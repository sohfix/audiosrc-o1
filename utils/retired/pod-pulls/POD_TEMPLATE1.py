import os
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
import configparser
import shutil
import threading
import logging
import time
import webbrowser
import feedparser
import requests
from datetime import datetime
from email.utils import parsedate_to_datetime

# Config paths and default tolerance (in MB)
CONFIG_PATH = r"C:\tools\config\podcasts.ini"
LOG_PATH = r"C:\tools\config\podcast_manager.log"
DEFAULT_TOLERANCE_MB = 5

# Set up logging to file
logger = logging.getLogger("PodcastManager")
logger.setLevel(logging.DEBUG)
fh = logging.FileHandler(LOG_PATH, encoding="utf-8")
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
fh.setFormatter(formatter)
logger.addHandler(fh)

class PodcastManagerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Podcast Manager")
        self.geometry("800x650")
        self.podcasts = {}  # {podcast_name: {"url": ..., "output": ...}}
        self.load_config()

        # Auto-update settings
        self.auto_update_enabled = getattr(self, "auto_update_enabled", False)
        self.auto_update_interval = getattr(self, "auto_update_interval", 60)  # in minutes
        self.auto_update_job = None

        self.build_gui()

    def load_config(self):
        self.config = configparser.ConfigParser()
        if not os.path.exists(CONFIG_PATH):
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            with open(CONFIG_PATH, "w") as f:
                f.write("")
        self.config.read(CONFIG_PATH)
        self.podcasts = {}
        if "Settings" in self.config:
            self.auto_update_enabled = self.config.getboolean("Settings", "auto_update_enabled", fallback=False)
            self.auto_update_interval = self.config.getint("Settings", "auto_update_interval", fallback=60)
        for section in self.config.sections():
            if section == "Settings":
                continue
            self.podcasts[section] = {
                "url": self.config.get(section, "url"),
                "output": self.config.get(section, "output")
            }

    def save_config(self):
        new_config = configparser.ConfigParser()
        new_config["Settings"] = {
            "auto_update_enabled": str(self.auto_update_enabled),
            "auto_update_interval": str(self.auto_update_interval)
        }
        for name, data in self.podcasts.items():
            new_config[name] = {
                "url": data["url"],
                "output": data["output"]
            }
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w") as f:
            new_config.write(f)

    def build_gui(self):
        # --- Top Frame: Manage Podcasts ---
        top_frame = tk.Frame(self)
        top_frame.pack(fill="x", pady=5)
        tk.Button(top_frame, text="Add Podcast", command=self.add_podcast).pack(side="left", padx=5)
        tk.Button(top_frame, text="Edit Podcast", command=self.edit_podcast).pack(side="left", padx=5)
        tk.Button(top_frame, text="Remove Podcast", command=self.remove_podcast).pack(side="left", padx=5)

        # --- Podcast List ---
        list_frame = tk.Frame(self)
        list_frame.pack(fill="x", padx=5)
        tk.Label(list_frame, text="Podcasts:").pack(anchor="w")
        self.podcast_listbox = tk.Listbox(list_frame, selectmode=tk.MULTIPLE, height=5)
        self.podcast_listbox.pack(fill="x")
        self.refresh_podcast_list()

        # --- Filtering Options ---
        filter_frame = tk.Frame(self)
        filter_frame.pack(fill="x", padx=5, pady=5)
        tk.Label(filter_frame, text="Max Episodes:").grid(row=0, column=0, padx=2)
        self.max_episodes_var = tk.StringVar()
        tk.Entry(filter_frame, textvariable=self.max_episodes_var, width=5).grid(row=0, column=1, padx=2)
        tk.Label(filter_frame, text="Filter After Date (YYYY-MM-DD):").grid(row=0, column=2, padx=2)
        self.filter_date_var = tk.StringVar()
        tk.Entry(filter_frame, textvariable=self.filter_date_var, width=12).grid(row=0, column=3, padx=2)
        tk.Label(filter_frame, text="Tolerance (MB):").grid(row=0, column=4, padx=2)
        self.tolerance_var = tk.StringVar(value=str(DEFAULT_TOLERANCE_MB))
        tk.Entry(filter_frame, textvariable=self.tolerance_var, width=5).grid(row=0, column=5, padx=2)

        # --- Update Buttons & Progress Bars ---
        update_frame = tk.Frame(self)
        update_frame.pack(fill="x", padx=5, pady=5)
        tk.Button(update_frame, text="Update Selected", command=self.update_selected).pack(side="left", padx=5)
        tk.Button(update_frame, text="Update All", command=self.update_all).pack(side="left", padx=5)

        # Progress for total tasks
        self.total_progress = ttk.Progressbar(update_frame, mode="determinate", length=200)
        self.total_progress.pack(side="left", padx=10)

        # Progress for individual file downloads
        self.file_progress = ttk.Progressbar(update_frame, mode="determinate", length=200)
        self.file_progress.pack(side="left", padx=10)

        # --- Storage Info ---
        self.storage_label = tk.Label(self, text="Storage: N/A")
        self.storage_label.pack(fill="x", padx=5)
        self.update_storage_info()

        # --- Auto-update Scheduling ---
        schedule_frame = tk.Frame(self)
        schedule_frame.pack(fill="x", padx=5, pady=5)
        self.auto_update_var = tk.BooleanVar(value=self.auto_update_enabled)
        tk.Checkbutton(schedule_frame, text="Auto Update", variable=self.auto_update_var, command=self.toggle_auto_update).pack(side="left", padx=5)
        tk.Label(schedule_frame, text="Interval (min):").pack(side="left", padx=2)
        self.interval_var = tk.StringVar(value=str(self.auto_update_interval))
        tk.Entry(schedule_frame, textvariable=self.interval_var, width=5).pack(side="left", padx=2)
        tk.Button(schedule_frame, text="Apply Schedule", command=self.apply_schedule).pack(side="left", padx=5)

        # --- Playback ---
        tk.Button(self, text="Play Episode", command=self.play_episode).pack(pady=5)

        # --- Log Info ---
        log_frame = tk.Frame(self)
        log_frame.pack(fill="both", expand=True, padx=5, pady=5)
        tk.Label(log_frame, text="Log:").pack(anchor="w")
        self.log_text = tk.Text(log_frame, height=10)
        self.log_text.pack(fill="both", expand=True)

    def refresh_podcast_list(self):
        self.podcast_listbox.delete(0, tk.END)
        for name in self.podcasts:
            self.podcast_listbox.insert(tk.END, name)

    def update_storage_info(self):
        drives = set()
        for data in self.podcasts.values():
            drive = os.path.splitdrive(data["output"])[0]
            if drive:
                drives.add(drive)
        info_list = []
        for drive in drives:
            try:
                total, used, free = shutil.disk_usage(drive + "\\")
                total_gb = total / (1024**3)
                free_gb = free / (1024**3)
                percent_used = (used / total) * 100
                info_list.append(
                    f"{drive}: {free_gb:.2f} GB free / {total_gb:.2f} GB total "
                    f"({percent_used:.1f}% used)"
                )
            except Exception:
                info_list.append(f"{drive}: Unavailable")
        self.storage_label.config(text=" | ".join(info_list))

    def log(self, message):
        logger.info(message)
        self.log_text.insert(tk.END, f"{datetime.now().strftime('%H:%M:%S')} - {message}\n")
        self.log_text.see(tk.END)

    def add_podcast(self):
        name = simpledialog.askstring("Add Podcast", "Enter podcast name:")
        if not name:
            return
        url = simpledialog.askstring("Add Podcast", "Enter RSS feed URL:")
        if not url:
            return
        output = filedialog.askdirectory(title="Select Output Directory")
        if not output:
            return
        self.podcasts[name] = {"url": url, "output": output}
        self.save_config()
        self.refresh_podcast_list()
        self.update_storage_info()
        self.log(f"Added podcast '{name}'.")

    def edit_podcast(self):
        selection = self.podcast_listbox.curselection()
        if len(selection) != 1:
            messagebox.showinfo("Edit Podcast", "Select exactly one podcast to edit.")
            return
        index = selection[0]
        name = self.podcast_listbox.get(index)
        url = simpledialog.askstring(
            "Edit Podcast",
            "Enter new RSS feed URL:",
            initialvalue=self.podcasts[name]["url"]
        )
        if not url:
            return
        output = filedialog.askdirectory(title="Select New Output Directory")
        if not output:
            return
        self.podcasts[name] = {"url": url, "output": output}
        self.save_config()
        self.refresh_podcast_list()
        self.update_storage_info()
        self.log(f"Edited podcast '{name}'.")

    def remove_podcast(self):
        selection = self.podcast_listbox.curselection()
        if not selection:
            messagebox.showinfo("Remove Podcast", "Select at least one podcast to remove.")
            return
        for index in reversed(selection):
            name = self.podcast_listbox.get(index)
            del self.podcasts[name]
            self.log(f"Removed podcast '{name}'.")
        self.save_config()
        self.refresh_podcast_list()
        self.update_storage_info()

    def update_selected(self):
        selection = self.podcast_listbox.curselection()
        if not selection:
            messagebox.showinfo("Update", "Select at least one podcast.")
            return
        podcasts_to_update = [self.podcast_listbox.get(i) for i in selection]
        threading.Thread(target=self.update_podcasts, args=(podcasts_to_update,), daemon=True).start()

    def update_all(self):
        threading.Thread(target=self.update_podcasts, args=(list(self.podcasts.keys()),), daemon=True).start()

    def update_podcasts(self, podcast_names):
        # Attempt to parse tolerance
        try:
            tolerance_mb = int(self.tolerance_var.get())
        except:
            tolerance_mb = DEFAULT_TOLERANCE_MB
        tolerance_bytes = tolerance_mb * 1024 * 1024

        # Filtering options
        max_episodes = int(self.max_episodes_var.get()) if self.max_episodes_var.get().isdigit() else None
        filter_date = None
        if self.filter_date_var.get():
            try:
                filter_date = datetime.strptime(self.filter_date_var.get(), "%Y-%m-%d")
            except:
                self.log("Invalid filter date format. Ignoring date filter.")

        tasks = []
        # Build a list of download tasks from all selected feeds
        for name in podcast_names:
            url = self.podcasts[name]["url"]
            feed = feedparser.parse(url)
            entries = self.filter_entries(feed.entries, max_episodes, filter_date)
            for entry in entries:
                if "enclosures" in entry:
                    for enc in entry.enclosures:
                        tasks.append((name, enc, self.podcasts[name]["output"]))

        total_tasks = len(tasks)
        if total_tasks == 0:
            self.log("No new episodes to download.")
            return

        # Setup total progress
        self.total_progress["maximum"] = total_tasks
        self.total_progress["value"] = 0

        for podcast_name, enc, output in tasks:
            file_url = enc.href
            filename = os.path.basename(file_url.split("?")[0])
            filepath = os.path.join(output, filename)

            # Check if file is already downloaded (within tolerance)
            if os.path.exists(filepath):
                try:
                    existing_size = os.path.getsize(filepath)
                    expected_size = int(enc.get("length", 0))
                    if expected_size > 0 and abs(existing_size - expected_size) <= tolerance_bytes:
                        self.log(f"Skipping already downloaded: {filename}")
                        self.total_progress["value"] += 1
                        self.update_idletasks()
                        continue
                except:
                    pass

            # Begin download
            self.log(f"Downloading {filename} from '{podcast_name}'...")
            try:
                with requests.get(file_url, stream=True, timeout=10) as r:
                    r.raise_for_status()

                    # Prepare the file-level progress
                    content_length = int(r.headers.get("content-length", 0))
                    downloaded = 0
                    if content_length > 0:
                        self.file_progress["maximum"] = content_length
                    else:
                        # If no content-length, we just reset for an indeterminate run
                        self.file_progress["maximum"] = 100  # any dummy value
                    self.file_progress["value"] = 0

                    os.makedirs(output, exist_ok=True)
                    with open(filepath, "wb") as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                # Update file progress if we know length
                                if content_length > 0:
                                    self.file_progress["value"] = downloaded
                                else:
                                    # If no length, just rotate progress somehow
                                    self.file_progress["value"] = (self.file_progress["value"] + 1) % 100
                                self.update_idletasks()

                self.log(f"Downloaded: {filename}")

            except Exception as e:
                self.log(f"Error downloading {filename}: {e}")

            # Move total progress up one “file”
            self.total_progress["value"] += 1
            # Reset file progress
            self.file_progress["value"] = 0

            self.update_idletasks()

        self.log("Update completed.")
        self.update_storage_info()

    def filter_entries(self, entries, max_episodes, filter_date):
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

    def play_episode(self):
        file_path = filedialog.askopenfilename(
            title="Select Episode File",
            filetypes=[("Audio Files", "*.mp3 *.m4a *.wav"), ("All Files", "*.*")]
        )
        if file_path:
            self.log(f"Playing: {file_path}")
            try:
                os.startfile(file_path)
            except Exception as e:
                self.log(f"Error playing file: {e}")
                webbrowser.open(file_path)

    def toggle_auto_update(self):
        self.auto_update_enabled = self.auto_update_var.get()
        if self.auto_update_enabled:
            self.schedule_auto_update()
            self.log("Auto update enabled.")
        else:
            if self.auto_update_job:
                self.after_cancel(self.auto_update_job)
                self.auto_update_job = None
            self.log("Auto update disabled.")
        self.save_config()

    def schedule_auto_update(self):
        try:
            interval = int(self.interval_var.get())
        except:
            interval = self.auto_update_interval
        self.auto_update_interval = interval
        self.save_config()
        self.update_all()
        self.auto_update_job = self.after(interval * 60000, self.schedule_auto_update)

    def apply_schedule(self):
        self.toggle_auto_update()
        self.log(f"Schedule applied: {self.auto_update_interval} minutes.")


if __name__ == "__main__":
    app = PodcastManagerApp()
    app.mainloop()
