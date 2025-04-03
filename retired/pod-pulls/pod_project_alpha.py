import sys
import os
import shutil
import time
import configparser
import logging
from datetime import datetime
from email.utils import parsedate_to_datetime

import requests
import feedparser

from PyQt5 import QtWidgets, QtCore, QtGui

# --------------------
#    CONFIG / LOGGING
# --------------------
CONFIG_PATH = r"C:\tools\config\podcasts.ini"
LOG_PATH = r"C:\tools\config\podcast_manager.log"
DEFAULT_TOLERANCE_MB = 5

logger = logging.getLogger("PodcastManager")
logger.setLevel(logging.DEBUG)
fh = logging.FileHandler(LOG_PATH, encoding="utf-8")
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
fh.setFormatter(formatter)
logger.addHandler(fh)

# --------------------
#      WORKER
# --------------------
class DownloadWorker(QtCore.QObject):
    """
    Download worker runs in a separate thread:
    - Receives a list of tasks from the main GUI
    - Downloads them, updating signals for file progress, total progress, and logs
    """
    progressTotalChanged = QtCore.pyqtSignal(int, int)  # (value, max)
    progressFileChanged = QtCore.pyqtSignal(int, int)   # (value, max)
    logMessage = QtCore.pyqtSignal(str)
    downloadInfo = QtCore.pyqtSignal(str)  # For speed, e.g.: "300 KB/s, 2.4 MB / 10 MB"

    def __init__(self, tasks, tolerance_bytes):
        super().__init__()
        self.tasks = tasks
        self.tolerance_bytes = tolerance_bytes

    def run(self):
        """
        Run the download process. This method should NOT block the main thread
        because it's executed within a separate QThread.
        """
        total_count = len(self.tasks)
        if total_count == 0:
            self.log("No new episodes to download.")
            # Trigger final “total progress” to show 0/0
            self.progressTotalChanged.emit(0, 0)
            return

        self.progressTotalChanged.emit(0, total_count)

        completed = 0
        for (podcast_name, file_url, filepath, expected_size) in self.tasks:
            filename = os.path.basename(file_url.split("?")[0])

            # Check if file already exists
            if os.path.exists(filepath):
                try:
                    existing_size = os.path.getsize(filepath)
                    if expected_size > 0 and abs(existing_size - expected_size) <= self.tolerance_bytes:
                        # Skip
                        self.log(f"Skipping already downloaded: {filename}")
                        completed += 1
                        self.progressTotalChanged.emit(completed, total_count)
                        continue
                except:
                    pass

            # Actually download
            self.log(f"Downloading {filename} from '{podcast_name}'...")
            self.progressFileChanged.emit(0, 1)  # reset file progress
            self.downloadInfo.emit("")          # clear file info line

            start_time = time.time()
            downloaded_bytes = 0

            try:
                with requests.get(file_url, stream=True, timeout=10) as r:
                    r.raise_for_status()
                    content_length = int(r.headers.get("content-length", 0))

                    # We know total file size
                    if content_length > 0:
                        self.progressFileChanged.emit(0, content_length)

                    os.makedirs(os.path.dirname(filepath), exist_ok=True)
                    with open(filepath, "wb") as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            if not chunk:
                                continue
                            f.write(chunk)
                            downloaded_bytes += len(chunk)

                            # Update file progress
                            if content_length > 0:
                                self.progressFileChanged.emit(downloaded_bytes, content_length)
                            else:
                                # If no content-length, just keep showing “something”
                                self.progressFileChanged.emit(0, 0)

                            # Show speed and partial stats
                            elapsed = time.time() - start_time
                            if elapsed > 0:
                                speed = downloaded_bytes / elapsed  # bytes/sec
                                # Convert speed to e.g. "300 KB/s"
                                speed_kb = speed / 1024
                                # Convert downloaded_bytes, content_length to MB
                                downloaded_mb = downloaded_bytes / (1024*1024)
                                total_mb = content_length / (1024*1024) if content_length > 0 else 0
                                if total_mb > 0:
                                    percent = (downloaded_mb / total_mb)*100
                                    info_str = f"{speed_kb:0.1f} KB/s, {downloaded_mb:0.2f} MB / {total_mb:0.2f} MB ({percent:0.1f}%)"
                                else:
                                    # unknown total
                                    info_str = f"{speed_kb:0.1f} KB/s, {downloaded_mb:0.2f} MB / ???"
                                self.downloadInfo.emit(info_str)

                self.log(f"Downloaded: {filename}")
            except Exception as e:
                self.log(f"Error downloading {filename}: {str(e)}")

            # Advance total progress
            completed += 1
            self.progressTotalChanged.emit(completed, total_count)

        self.log("Update completed.")

    def log(self, msg):
        logger.info(msg)
        self.logMessage.emit(msg)

# --------------------
#    SETTINGS DIALOG
# --------------------
class SettingsDialog(QtWidgets.QDialog):
    """
    Dialog that allows toggling dark mode, configuring auto-update, etc.
    """
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.config = config

        layout = QtWidgets.QVBoxLayout(self)

        # Dark Mode checkbox
        self.darkModeCheck = QtWidgets.QCheckBox("Enable Dark Mode")
        self.darkModeCheck.setChecked(self.config.getboolean("Settings", "dark_mode", fallback=False))
        layout.addWidget(self.darkModeCheck)

        # Auto-update checkbox
        self.autoUpdateCheck = QtWidgets.QCheckBox("Enable Auto Update")
        self.autoUpdateCheck.setChecked(self.config.getboolean("Settings", "auto_update_enabled", fallback=False))
        layout.addWidget(self.autoUpdateCheck)

        # Interval spin box
        interval_label = QtWidgets.QLabel("Auto-update interval (minutes):")
        layout.addWidget(interval_label)
        self.intervalSpin = QtWidgets.QSpinBox()
        self.intervalSpin.setRange(1, 1440)  # 1 minute to 24 hours
        self.intervalSpin.setValue(self.config.getint("Settings", "auto_update_interval", fallback=60))
        layout.addWidget(self.intervalSpin)

        # OK/Cancel
        btn_layout = QtWidgets.QHBoxLayout()
        btn_ok = QtWidgets.QPushButton("OK")
        btn_cancel = QtWidgets.QPushButton("Cancel")
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)

    def accept(self):
        # Save settings to config
        dark_mode = self.darkModeCheck.isChecked()
        auto_enabled = self.autoUpdateCheck.isChecked()
        interval = self.intervalSpin.value()

        if "Settings" not in self.config:
            self.config["Settings"] = {}

        self.config["Settings"]["dark_mode"] = str(dark_mode)
        self.config["Settings"]["auto_update_enabled"] = str(auto_enabled)
        self.config["Settings"]["auto_update_interval"] = str(interval)

        super().accept()

# --------------------
#    MAIN WINDOW
# --------------------
class PodcastManagerApp(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Podcast Manager (PyQt)")

        # Load config
        self.config = configparser.ConfigParser()
        self.loadConfig()

        self.podcasts = {}
        self.loadPodcastsFromConfig()

        # Auto-update
        self.autoUpdateTimer = QtCore.QTimer(self)
        self.autoUpdateTimer.timeout.connect(self.onAutoUpdate)

        self.centralWidget = QtWidgets.QWidget()
        self.setCentralWidget(self.centralWidget)
        main_layout = QtWidgets.QVBoxLayout(self.centralWidget)

        # -- Top buttons (Add, Edit, Remove, Settings) --
        top_btn_layout = QtWidgets.QHBoxLayout()
        btn_add = QtWidgets.QPushButton("Add Podcast")
        btn_edit = QtWidgets.QPushButton("Edit Podcast")
        btn_remove = QtWidgets.QPushButton("Remove Podcast")
        btn_settings = QtWidgets.QPushButton("Settings")

        btn_add.clicked.connect(self.addPodcast)
        btn_edit.clicked.connect(self.editPodcast)
        btn_remove.clicked.connect(self.removePodcast)
        btn_settings.clicked.connect(self.openSettings)

        top_btn_layout.addWidget(btn_add)
        top_btn_layout.addWidget(btn_edit)
        top_btn_layout.addWidget(btn_remove)
        top_btn_layout.addWidget(btn_settings)
        main_layout.addLayout(top_btn_layout)

        # -- Podcast list --
        self.podcastList = QtWidgets.QListWidget()
        self.refreshPodcastList()
        main_layout.addWidget(QtWidgets.QLabel("Podcasts:"))
        main_layout.addWidget(self.podcastList)

        # -- Filtering row --
        filter_layout = QtWidgets.QHBoxLayout()

        filter_layout.addWidget(QtWidgets.QLabel("Max Episodes:"))
        self.maxEpisodesEdit = QtWidgets.QLineEdit()
        self.maxEpisodesEdit.setFixedWidth(50)
        filter_layout.addWidget(self.maxEpisodesEdit)

        filter_layout.addWidget(QtWidgets.QLabel("Filter After Date (YYYY-MM-DD):"))
        self.filterDateEdit = QtWidgets.QLineEdit()
        self.filterDateEdit.setFixedWidth(100)
        filter_layout.addWidget(self.filterDateEdit)

        filter_layout.addWidget(QtWidgets.QLabel("Tolerance (MB):"))
        self.toleranceEdit = QtWidgets.QLineEdit(str(DEFAULT_TOLERANCE_MB))
        self.toleranceEdit.setFixedWidth(50)
        filter_layout.addWidget(self.toleranceEdit)

        main_layout.addLayout(filter_layout)

        # -- Update row (buttons + progress bars + speed info) --
        update_layout = QtWidgets.QHBoxLayout()

        btn_update_selected = QtWidgets.QPushButton("Update Selected")
        btn_update_all = QtWidgets.QPushButton("Update All")
        btn_update_selected.clicked.connect(self.updateSelected)
        btn_update_all.clicked.connect(self.updateAll)
        update_layout.addWidget(btn_update_selected)
        update_layout.addWidget(btn_update_all)

        # Overall progress
        self.progressTotal = QtWidgets.QProgressBar()
        self.progressTotal.setTextVisible(True)
        self.progressTotal.setFormat("0 / 0")
        self.progressTotal.setValue(0)
        update_layout.addWidget(self.progressTotal)

        # File-level progress
        self.progressFile = QtWidgets.QProgressBar()
        self.progressFile.setTextVisible(True)
        self.progressFile.setFormat("0 / 0")
        self.progressFile.setValue(0)
        update_layout.addWidget(self.progressFile)

        main_layout.addLayout(update_layout)

        # Extra label to show speed and partial stats
        self.downloadInfoLabel = QtWidgets.QLabel("")
        main_layout.addWidget(self.downloadInfoLabel)

        # -- Storage info --
        self.storageLabel = QtWidgets.QLabel("Storage: N/A")
        main_layout.addWidget(self.storageLabel)
        self.updateStorageInfo()

        # -- Playback button --
        btn_play = QtWidgets.QPushButton("Play Episode")
        btn_play.clicked.connect(self.playEpisode)
        main_layout.addWidget(btn_play)

        # -- Log text area --
        main_layout.addWidget(QtWidgets.QLabel("Log:"))
        self.logText = QtWidgets.QTextEdit()
        self.logText.setReadOnly(True)
        main_layout.addWidget(self.logText)

        # If dark mode is enabled, apply a style
        if self.getDarkMode():
            self.applyDarkMode()

        # If auto-update is enabled, start the timer
        if self.getAutoUpdateEnabled():
            self.startAutoUpdateTimer()

        self.show()

    # -----------
    #   CONFIG
    # -----------
    def loadConfig(self):
        if not os.path.exists(os.path.dirname(CONFIG_PATH)):
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        if not os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "w") as f:
                f.write("")
        self.config.read(CONFIG_PATH)

    def saveConfig(self):
        with open(CONFIG_PATH, "w") as f:
            self.config.write(f)

    def getDarkMode(self):
        return self.config.getboolean("Settings", "dark_mode", fallback=False)

    def getAutoUpdateEnabled(self):
        return self.config.getboolean("Settings", "auto_update_enabled", fallback=False)

    def getAutoUpdateInterval(self):
        return self.config.getint("Settings", "auto_update_interval", fallback=60)

    # -----------
    #  PODCASTS
    # -----------
    def loadPodcastsFromConfig(self):
        self.podcasts.clear()
        for section in self.config.sections():
            if section == "Settings":
                continue
            self.podcasts[section] = {
                "url": self.config.get(section, "url"),
                "output": self.config.get(section, "output")
            }

    def savePodcastsToConfig(self):
        # Remove old sections
        for section in self.config.sections():
            if section != "Settings":
                self.config.remove_section(section)
        # Add them fresh
        for name, data in self.podcasts.items():
            self.config[name] = {
                "url": data["url"],
                "output": data["output"]
            }
        self.saveConfig()

    def refreshPodcastList(self):
        self.podcastList.clear()
        for name in self.podcasts:
            self.podcastList.addItem(name)

    # -----------
    #   LOGGING
    # -----------
    def log(self, message):
        logger.info(message)
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.logText.append(f"{timestamp} - {message}")

    # -----------
    #   ACTIONS
    # -----------
    def addPodcast(self):
        name, ok = QtWidgets.QInputDialog.getText(self, "Add Podcast", "Enter podcast name:")
        if not ok or not name.strip():
            return
        url, ok = QtWidgets.QInputDialog.getText(self, "Add Podcast", "Enter RSS feed URL:")
        if not ok or not url.strip():
            return
        output = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if not output:
            return
        self.podcasts[name] = {"url": url, "output": output}
        self.savePodcastsToConfig()
        self.refreshPodcastList()
        self.updateStorageInfo()
        self.log(f"Added podcast '{name}'.")

    def editPodcast(self):
        item = self.podcastList.currentItem()
        if not item:
            QtWidgets.QMessageBox.information(self, "Edit Podcast", "Select a single podcast to edit.")
            return
        name = item.text()
        current_url = self.podcasts[name]["url"]
        current_output = self.podcasts[name]["output"]

        url, ok = QtWidgets.QInputDialog.getText(self, "Edit Podcast", "Enter new RSS feed URL:", text=current_url)
        if not ok or not url.strip():
            return
        output = QtWidgets.QFileDialog.getExistingDirectory(self, "Select New Output Directory", current_output)
        if not output:
            return
        self.podcasts[name] = {"url": url, "output": output}
        self.savePodcastsToConfig()
        self.refreshPodcastList()
        self.updateStorageInfo()
        self.log(f"Edited podcast '{name}'.")

    def removePodcast(self):
        selected_items = self.podcastList.selectedItems()
        if not selected_items:
            QtWidgets.QMessageBox.information(self, "Remove Podcast", "Select at least one podcast to remove.")
            return
        for item in selected_items:
            name = item.text()
            if name in self.podcasts:
                del self.podcasts[name]
                self.log(f"Removed podcast '{name}'.")
        self.savePodcastsToConfig()
        self.refreshPodcastList()
        self.updateStorageInfo()

    def updateSelected(self):
        selected_items = self.podcastList.selectedItems()
        if not selected_items:
            QtWidgets.QMessageBox.information(self, "Update", "Select at least one podcast.")
            return
        names = [item.text() for item in selected_items]
        self.startDownloadProcess(names)

    def updateAll(self):
        names = list(self.podcasts.keys())
        self.startDownloadProcess(names)

    def playEpisode(self):
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select Episode File", "", "Audio Files (*.mp3 *.m4a *.wav);;All Files (*.*)"
        )
        if file_path:
            self.log(f"Playing: {file_path}")
            try:
                # On Windows, this works. For cross-platform, might need more robust approach.
                os.startfile(file_path)
            except Exception as e:
                self.log(f"Error playing file: {str(e)}")
                import webbrowser
                webbrowser.open(file_path)

    # -----------
    #   STORAGE
    # -----------
    def updateStorageInfo(self):
        drives = set()
        for data in self.podcasts.values():
            drive = os.path.splitdrive(data["output"])[0]
            if drive:
                drives.add(drive)
        info_list = []
        for drive in drives:
            if not drive:
                continue
            try:
                total, used, free = shutil.disk_usage(drive + "\\")
                total_gb = total / (1024**3)
                free_gb = free / (1024**3)
                percent_used = (used / total) * 100
                info_list.append(f"{drive}: {free_gb:.2f} GB free / {total_gb:.2f} GB total ({percent_used:.1f}% used)")
            except:
                info_list.append(f"{drive}: Unavailable")
        self.storageLabel.setText(" | ".join(info_list))

    # -----------
    #   DOWNLOAD PROCESS
    # -----------
    def startDownloadProcess(self, podcast_names):
        # Attempt to parse tolerance
        try:
            tolerance_mb = int(self.toleranceEdit.text())
        except:
            tolerance_mb = DEFAULT_TOLERANCE_MB
        tolerance_bytes = tolerance_mb * 1024 * 1024

        # Filtering options
        max_episodes = None
        if self.maxEpisodesEdit.text().isdigit():
            max_episodes = int(self.maxEpisodesEdit.text())
        filter_date = None
        if self.filterDateEdit.text().strip():
            try:
                filter_date = datetime.strptime(self.filterDateEdit.text(), "%Y-%m-%d")
            except:
                self.log("Invalid filter date format. Ignoring date filter.")

        # Build tasks
        tasks = []
        for name in podcast_names:
            url = self.podcasts[name]["url"]
            feed = feedparser.parse(url)
            entries = self.filterEntries(feed.entries, max_episodes, filter_date)
            for entry in entries:
                if "enclosures" in entry:
                    for enc in entry.enclosures:
                        file_url = enc.href
                        output_dir = self.podcasts[name]["output"]
                        filename = os.path.basename(file_url.split("?")[0])
                        filepath = os.path.join(output_dir, filename)
                        # Some feeds provide a length property
                        expected_size = int(enc.get("length", 0)) if enc.get("length") else 0
                        tasks.append((name, file_url, filepath, expected_size))

        # Reset UI progress
        self.progressTotal.setValue(0)
        self.progressTotal.setFormat("0 / %d" % len(tasks) if tasks else "0 / 0")
        self.progressFile.setValue(0)
        self.progressFile.setFormat("0 / 0")
        self.downloadInfoLabel.setText("")

        # Create worker & thread
        self.downloadThread = QtCore.QThread(self)
        self.downloadWorker = DownloadWorker(tasks, tolerance_bytes)
        self.downloadWorker.moveToThread(self.downloadThread)

        # Connect signals
        self.downloadThread.started.connect(self.downloadWorker.run)
        self.downloadWorker.progressTotalChanged.connect(self.onTotalProgress)
        self.downloadWorker.progressFileChanged.connect(self.onFileProgress)
        self.downloadWorker.logMessage.connect(self.onLogMessage)
        self.downloadWorker.downloadInfo.connect(self.onDownloadInfo)

        # When worker finishes, delete the worker + thread, update storage
        self.downloadThread.finished.connect(self.downloadWorker.deleteLater)
        self.downloadThread.finished.connect(self.downloadThread.deleteLater)
        self.downloadWorker.logMessage.connect(lambda msg: self.updateStorageInfo())

        # On completion or errors, the worker itself calls "log(...)", but we can stop the thread
        # by letting "run" end naturally.
        # We'll connect a small signal from the worker to stop the thread if we want,
        # but in this example it just completes the loop and ends.

        self.downloadThread.start()

    @QtCore.pyqtSlot(int, int)
    def onTotalProgress(self, value, maximum):
        if maximum > 0:
            self.progressTotal.setMaximum(maximum)
            self.progressTotal.setValue(value)
            self.progressTotal.setFormat(f"{value} / {maximum}")
        else:
            self.progressTotal.setMaximum(1)
            self.progressTotal.setValue(0)
            self.progressTotal.setFormat("0 / 0")

        # If done
        if value == maximum:
            # End the thread
            self.downloadThread.quit()

    @QtCore.pyqtSlot(int, int)
    def onFileProgress(self, value, maximum):
        if maximum > 0:
            self.progressFile.setMaximum(maximum)
            self.progressFile.setValue(value)
            # Show e.g. "10 KB / 100 KB"
            if value < 1024*1024:
                # show in KB
                self.progressFile.setFormat(f"{value//1024} KB / {maximum//1024} KB")
            else:
                # show in MB
                val_mb = value / (1024*1024)
                max_mb = maximum / (1024*1024)
                self.progressFile.setFormat(f"{val_mb:0.1f} MB / {max_mb:0.1f} MB")
        else:
            # Indeterminate or unknown file length
            self.progressFile.setMaximum(0)  # QProgressBar "busy" mode
            self.progressFile.setFormat("Unknown size")

    @QtCore.pyqtSlot(str)
    def onLogMessage(self, msg):
        self.log(msg)

    @QtCore.pyqtSlot(str)
    def onDownloadInfo(self, info_str):
        self.downloadInfoLabel.setText(info_str)

    def filterEntries(self, entries, max_episodes, filter_date):
        def get_date(entry):
            try:
                if "published" in entry:
                    return parsedate_to_datetime(entry.published)
                elif "updated" in entry:
                    return parsedate_to_datetime(entry.updated)
            except:
                return datetime.min
            return datetime.min

        sorted_entries = sorted(entries, key=get_date, reverse=True)
        filtered = []
        for entry in sorted_entries:
            if filter_date:
                if get_date(entry) < filter_date:
                    continue
            filtered.append(entry)
            if max_episodes and len(filtered) >= max_episodes:
                break
        return filtered

    # -----------
    #   SETTINGS
    # -----------
    def openSettings(self):
        dialog = SettingsDialog(self.config, self)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            # The dialog has already saved changes to self.config
            self.saveConfig()
            # Reload things like dark mode or timers
            self.applyDarkMode() if self.getDarkMode() else self.clearDarkMode()

            if self.getAutoUpdateEnabled():
                self.startAutoUpdateTimer()
            else:
                self.stopAutoUpdateTimer()

    def applyDarkMode(self):
        dark_qss = """
        QMainWindow, QWidget {
            background-color: #2b2b2b;
            color: #ffffff;
        }
        QLineEdit, QTextEdit, QPlainTextEdit {
            background-color: #3c3c3c;
            color: #ffffff;
        }
        QPushButton {
            background-color: #444444;
            color: #ffffff;
        }
        QProgressBar {
            border: 1px solid #111111;
            background: #3c3c3c;
            text-align: center;
        }
        QProgressBar::chunk {
            background-color: #0080ff;
        }
        QListWidget, QTreeWidget {
            background-color: #3c3c3c;
            color: #ffffff;
        }
        """
        self.setStyleSheet(dark_qss)

    def clearDarkMode(self):
        self.setStyleSheet("")

    # -----------
    #   AUTO UPDATE
    # -----------
    def startAutoUpdateTimer(self):
        interval = self.getAutoUpdateInterval()
        self.autoUpdateTimer.start(interval * 60000)  # minutes -> ms
        self.log(f"Auto-update timer started ({interval} min).")

    def stopAutoUpdateTimer(self):
        self.autoUpdateTimer.stop()
        self.log("Auto-update timer stopped.")

    def onAutoUpdate(self):
        self.log("Auto-update triggered.")
        self.updateAll()

# --------------------
#   MAIN ENTRY
# --------------------
if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)

    # Optionally set a default font (some people prefer bigger UI text)
    font = QtGui.QFont("Segoe UI", 9)
    app.setFont(font)

    window = PodcastManagerApp()
    window.resize(1000, 700)
    window.show()

    sys.exit(app.exec_())
