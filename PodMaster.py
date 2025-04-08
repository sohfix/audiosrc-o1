import configparser
import csv
import datetime
import io
import os
import shutil
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

import feedparser
import matplotlib
import requests
import vlc  # requires python-vlc
from mutagen.id3 import ID3
from PIL import Image, ImageTk

matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

GUI_THEME = "alt"
# Constants for config file paths
CONFIG_DIR = r"C:\tools\config"
USERS_CONFIG_PATH = os.path.join(CONFIG_DIR, "users.ini")
DEFAULT_TOLERANCE_MB = 7


def format_bytes(num_bytes):
    """Return a human-friendly string for bytes (in GB, MB, KB, or B)."""
    if num_bytes >= 1024**3:
        return f"{num_bytes/1024**3:.2f} GB"
    elif num_bytes >= 1024**2:
        return f"{num_bytes/1024**2:.2f} MB"
    elif num_bytes >= 1024:
        return f"{num_bytes/1024:.2f} KB"
    else:
        return f"{num_bytes} B"


class PodcastManagerApp:
    def __init__(self, root, username):
        self.root = root
        self.username = username
        self.root.title(f"Podcast Manager - User: {self.username}")
        self.root.geometry("840x600")

        self.stop_flag = False
        self.switch_user_requested = False

        # For usage metrics file
        self.metrics_file = os.path.join(
            CONFIG_DIR, f"played_episodes_{self.username}.csv"
        )
        if not os.path.exists(self.metrics_file):
            with open(self.metrics_file, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["Title", "FilePath", "PlayedAt"])

        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        # Set user-specific podcasts config path
        self.CONFIG_PATH = os.path.join(CONFIG_DIR, f"pods_{self.username}.ini")
        self.podcasts = {}
        self.check_vars = {}

        self.ensure_config()
        self.load_config()

        # Playlist: list of tuples (title, filepath)
        self.playlist = []

        # Interval for checking drive connectivity (milliseconds)
        self.drive_check_interval = 30000  # 30 seconds
        # Dictionary for status labels (green/red) for each podcast
        self.drive_status_labels = {}

        # Build the GUI
        self.build_gui()

        # Create VLC media player instance
        self.vlc_instance = vlc.Instance()
        self.media_player = self.vlc_instance.media_player_new()

        # Current playing episode info
        self.current_episode = None
        self.play_start_time = None

    def ensure_config(self):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        if not os.path.exists(self.CONFIG_PATH):
            with open(self.CONFIG_PATH, "w") as f:
                f.write("")

    def load_config(self):
        self.config = configparser.ConfigParser()
        self.config.read(self.CONFIG_PATH)
        for section in self.config.sections():
            self.podcasts[section] = {
                "url": self.config[section]["url"],
                "output": self.config[section]["output"],
            }

    def save_config(self):
        with open(self.CONFIG_PATH, "w") as configfile:
            self.config.write(configfile)

    def build_gui(self):
        # STATUS BAR AT THE TOP:
        status_frame = ttk.Frame(self.root)
        status_frame.pack(side="top", fill="x", padx=5, pady=5)

        self.progress_label = ttk.Label(status_frame, text="Ready")
        self.progress_label.pack(side="left", padx=10)

        style = ttk.Style()
        style.theme_use(GUI_THEME)

        style.configure(
            "Custom.Horizontal.TProgressbar",
            troughcolor="lightgray",
            background="blue",
            thickness=20,
        )
        self.progress_bar = ttk.Progressbar(
            status_frame,
            length=300,
            mode="determinate",
            style="Custom.Horizontal.TProgressbar",
        )
        self.progress_bar.pack(side="left", padx=10, pady=5)

        self.file_progress_label = ttk.Label(status_frame, text="", font=("Arial", 9))
        self.file_progress_label.pack(side="left", padx=10)

        ttk.Button(
            status_frame, text="Stop After Next", command=self.set_stop_flag
        ).pack(side="left", padx=10)

        # NOTEBOOK FOR TABS:
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True)

        # Podcasts Tab
        self.tab_podcasts = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_podcasts, text="Podcasts")
        self.build_podcast_tab(self.tab_podcasts)

        # Storage Tab
        self.tab_storage = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_storage, text="Storage")
        self.build_storage_tab(self.tab_storage)

        # Activity Tab
        self.tab_activity = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_activity, text="Activity")
        self.build_activity_tab(self.tab_activity)

        # Player Tab
        self.tab_player = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_player, text="Player")
        self.build_player_tab(self.tab_player)

    def build_activity_tab(self, parent):
        self.log_text = ScrolledText(parent, height=20, wrap="word")
        self.log_text.pack(fill="both", expand=True, padx=5, pady=5)

    # ------------------ Player Tab ------------------
    def build_player_tab(self, parent):
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True, padx=5, pady=5)

        # Album art display
        self.album_art_label = tk.Label(frame)
        self.album_art_label.pack(pady=5)

        # Playlist area
        playlist_frame = ttk.LabelFrame(frame, text="Playlist")
        playlist_frame.pack(fill="both", expand=True, padx=5, pady=5)

        self.playlist_listbox = tk.Listbox(playlist_frame, height=6)
        self.playlist_listbox.pack(
            side="left", fill="both", expand=True, padx=5, pady=5
        )
        self.playlist_listbox.bind(
            "<Double-Button-1>", lambda e: self.load_selected_playlist_item()
        )

        pl_scroll = ttk.Scrollbar(
            playlist_frame, orient="vertical", command=self.playlist_listbox.yview
        )
        pl_scroll.pack(side="right", fill="y")
        self.playlist_listbox.config(yscrollcommand=pl_scroll.set)

        # Buttons to add/remove from playlist
        pl_btn_frame = ttk.Frame(frame)
        pl_btn_frame.pack(pady=5)
        ttk.Button(pl_btn_frame, text="Add File", command=self.add_to_playlist).grid(
            row=0, column=0, padx=5
        )
        ttk.Button(
            pl_btn_frame,
            text="Remove Selected",
            command=self.remove_selected_playlist_item,
        ).grid(row=0, column=1, padx=5)

        # Search by MP3 title
        search_frame = ttk.Frame(frame)
        search_frame.pack(pady=5)
        ttk.Label(search_frame, text="Search Title:").grid(row=0, column=0, padx=5)

        self.search_var = tk.StringVar()
        ttk.Entry(search_frame, textvariable=self.search_var, width=30).grid(
            row=0, column=1, padx=5
        )
        ttk.Button(search_frame, text="Search", command=self.search_playlist).grid(
            row=0, column=2, padx=5
        )

        # Playback controls
        controls_frame = ttk.Frame(frame)
        controls_frame.pack(pady=10)
        ttk.Button(controls_frame, text="⏪ 15s", command=self.skip_backward).grid(
            row=0, column=0, padx=5
        )
        ttk.Button(controls_frame, text="►", command=self.play_audio, width=5).grid(
            row=0, column=1, padx=5
        )
        ttk.Button(controls_frame, text="⏸", command=self.pause_audio, width=5).grid(
            row=0, column=2, padx=5
        )
        ttk.Button(controls_frame, text="■", command=self.stop_audio, width=5).grid(
            row=0, column=3, padx=5
        )
        ttk.Button(controls_frame, text="15s ⏩", command=self.skip_forward).grid(
            row=0, column=4, padx=5
        )

        # Volume slider
        vol_frame = ttk.Frame(frame)
        vol_frame.pack(pady=5)
        ttk.Label(vol_frame, text="Volume:").pack(side="left")

        self.volume_var = tk.DoubleVar(value=100)
        ttk.Scale(
            vol_frame,
            from_=0,
            to=100,
            variable=self.volume_var,
            command=lambda e: self.set_volume(),
        ).pack(side="left", fill="x", expand=True, padx=5)

    def add_to_playlist(self):
        filepath = filedialog.askopenfilename(
            title="Select Audio File",
            filetypes=[("Audio Files", "*.mp3 *.wav *.m4a *.ogg")],
        )
        if filepath:
            title = os.path.splitext(os.path.basename(filepath))[0]
            if filepath.lower().endswith(".mp3"):
                try:
                    tags = ID3(filepath)
                    if "TIT2" in tags:
                        title = tags["TIT2"].text[0]
                except Exception as e:
                    self.log(f"Error reading MP3 title: {e}")
            self.playlist.append((title, filepath))
            self.playlist_listbox.insert(tk.END, title)

    def remove_selected_playlist_item(self):
        selection = self.playlist_listbox.curselection()
        if selection:
            idx = selection[0]
            self.playlist_listbox.delete(idx)
            del self.playlist[idx]

    def load_selected_playlist_item(self):
        selection = self.playlist_listbox.curselection()
        if selection:
            idx = selection[0]
            title, filepath = self.playlist[idx]
            self.load_audio_file(filepath)

    # ------------------ Storage Tab ------------------
    def build_storage_tab(self, parent):
        ttk.Button(parent, text="Refresh Storage Info", command=self.show_storage).pack(
            pady=5
        )
        self.storage_chart_frame = ttk.Frame(parent)
        self.storage_chart_frame.pack(fill="both", expand=True)
        self.show_storage()

    def show_storage(self):
        for widget in self.storage_chart_frame.winfo_children():
            widget.destroy()

        drives = {}
        for data in self.podcasts.values():
            drive = os.path.splitdrive(data["output"])[0]
            if drive not in drives:
                try:
                    total, used, free = shutil.disk_usage(drive + os.sep)
                    drives[drive] = (total, used, free)
                except Exception:
                    # Could not access drive
                    drives[drive] = (0, 0, 0)

        # Adjust figure size based on number of drives
        fig = Figure(figsize=(8, max(1.5 * len(drives), 2)), dpi=100)
        ax = fig.add_subplot(111)

        drive_labels = []
        used_space = []
        free_space = []

        for drive, (total, used, free) in drives.items():
            drive_labels.append(f"{drive} ({format_bytes(total)})")
            used_space.append(used / (1024**3))  # GB
            free_space.append(free / (1024**3))  # GB

        ax.barh(drive_labels, used_space, label="Used Space (GB)")
        ax.barh(drive_labels, free_space, left=used_space, label="Free Space (GB)")

        for i, (u, f) in enumerate(zip(used_space, free_space)):
            ax.text(
                u / 2,
                i,
                f"{u:.1f} GB Used",
                va="center",
                ha="center",
                color="white",
                fontsize=8,
                fontweight="bold",
            )
            ax.text(
                u + f / 2,
                i,
                f"{f:.1f} GB Free",
                va="center",
                ha="center",
                color="black",
                fontsize=8,
                fontweight="bold",
            )

        ax.set_xlabel("Storage (GB)")
        ax.set_title("Drive Storage Usage")
        ax.legend()
        ax.grid(axis="x", linestyle="--", alpha=0.5)

        fig.tight_layout()
        canvas = FigureCanvasTkAgg(fig, master=self.storage_chart_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)

    def search_playlist(self):
        query = self.search_var.get().strip().lower()
        self.playlist_listbox.delete(0, tk.END)
        for title, path in self.playlist:
            if query in title.lower():
                self.playlist_listbox.insert(tk.END, title)

    def load_audio_file(self, filepath=None):
        if not filepath:
            filepath = filedialog.askopenfilename(
                title="Select Audio File",
                filetypes=[("Audio Files", "*.mp3 *.wav *.m4a *.ogg")],
            )
        if filepath:
            media = self.vlc_instance.media_new(filepath)
            self.media_player.set_media(media)
            self.current_episode = filepath
            self.play_start_time = time.time()
            self.log(f"Loaded file: {os.path.basename(filepath)}")
            if filepath.lower().endswith(".mp3"):
                try:
                    tags = ID3(filepath)
                    apic = None
                    for key in tags.keys():
                        if key.startswith("APIC"):
                            apic = tags.get(key)
                            break
                    if apic is not None:
                        art_data = apic.data
                        image = Image.open(io.BytesIO(art_data))
                        image = image.resize((100, 100))
                        photo = ImageTk.PhotoImage(image)
                        self.album_art_label.config(image=photo)
                        self.album_art_label.image = photo
                    else:
                        self.album_art_label.config(image="")
                except Exception as e:
                    self.log(f"Could not load album art: {e}")

    def play_audio(self):
        self.media_player.play()
        self.log("Playing audio.")

    def pause_audio(self):
        self.media_player.pause()
        self.log("Audio paused.")

    def stop_audio(self):
        self.media_player.stop()
        self.log("Audio stopped.")
        if self.current_episode and self.play_start_time:
            played_duration = time.time() - self.play_start_time
            if played_duration > 30:
                title = os.path.splitext(os.path.basename(self.current_episode))[0]
                if self.current_episode.lower().endswith(".mp3"):
                    try:
                        tags = ID3(self.current_episode)
                        if "TIT2" in tags:
                            title = tags["TIT2"].text[0]
                    except Exception:
                        pass
            self.current_episode = None
            self.play_start_time = None

    def skip_forward(self):
        current_time = self.media_player.get_time()
        self.media_player.set_time(current_time + 15000)
        self.log("Skipped forward 15 seconds.")

    def skip_backward(self):
        current_time = self.media_player.get_time()
        new_time = max(0, current_time - 15000)
        self.media_player.set_time(new_time)
        self.log("Skipped backward 15 seconds.")

    def set_volume(self):
        vol = int(self.volume_var.get())
        self.media_player.audio_set_volume(vol)

    # ------------------ Podcasts Tab ------------------
    def build_podcast_tab(self, parent):
        top_frame = ttk.Frame(parent)
        top_frame.pack(fill="x", pady=5, padx=5)

        ttk.Button(top_frame, text="Add", command=self.add_podcast).pack(
            side="left", padx=3
        )
        ttk.Button(top_frame, text="Edit", command=self.edit_podcast).pack(
            side="left", padx=3
        )
        ttk.Button(top_frame, text="Remove", command=self.remove_podcast).pack(
            side="left", padx=3
        )
        ttk.Button(
            top_frame, text="Download One-Off", command=self.download_one_off
        ).pack(side="left", padx=3)

        tol_frame = ttk.Frame(parent)
        tol_frame.pack(fill="x", padx=5, pady=5)
        ttk.Label(tol_frame, text="Tolerance (MB):").pack(side="left")
        self.tolerance_var = tk.StringVar(value=str(DEFAULT_TOLERANCE_MB))
        ttk.Entry(tol_frame, textvariable=self.tolerance_var, width=5).pack(
            side="left", padx=3
        )

        filter_frame = ttk.Frame(parent)
        filter_frame.pack(fill="x", padx=5, pady=5)
        ttk.Label(filter_frame, text="Max Episodes:").pack(side="left")
        self.max_episodes_var = tk.StringVar()
        ttk.Entry(filter_frame, textvariable=self.max_episodes_var, width=5).pack(
            side="left", padx=3
        )

        ttk.Label(filter_frame, text="Filter Date (YYYY-MM-DD):").pack(
            side="left", padx=(10, 0)
        )
        self.filter_date_var = tk.StringVar()
        ttk.Entry(filter_frame, textvariable=self.filter_date_var, width=12).pack(
            side="left", padx=3
        )

        update_frame = ttk.Frame(parent)
        update_frame.pack(fill="x", padx=5, pady=5)
        ttk.Button(
            update_frame, text="Update Selected", command=self.update_selected
        ).pack(side="left", padx=3)

        list_frame = ttk.Frame(parent)
        list_frame.pack(fill="both", expand=False, padx=5, pady=5)

        canvas = tk.Canvas(list_frame, height=250)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        self.podcast_list_frame = ttk.Frame(canvas)
        self.podcast_list_frame.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=self.podcast_list_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Build the listing
        self.refresh_list()

        # Schedule repeated drive checks
        self.root.after(self.drive_check_interval, self.check_drives)

    def refresh_list(self):
        for widget in self.podcast_list_frame.winfo_children():
            widget.destroy()
        self.check_vars = {}
        # clear out any previous status labels
        self.drive_status_labels.clear()

        for idx, (name, data) in enumerate(self.podcasts.items()):
            var = tk.BooleanVar()
            # The main checkbutton for this podcast
            chk = ttk.Checkbutton(
                self.podcast_list_frame,
                text=f"{name} | {data['url']} | {data['output']}",
                variable=var,
            )
            chk.grid(row=idx, column=0, sticky="w", padx=2, pady=2)
            self.check_vars[name] = var

            # Status label for drive connectivity
            status_lbl = ttk.Label(self.podcast_list_frame, text="...")
            status_lbl.grid(row=idx, column=1, sticky="w", padx=8)
            self.drive_status_labels[name] = status_lbl

    def check_drives(self):
        for name, data in self.podcasts.items():
            drive = os.path.splitdrive(data["output"])[0]  # e.g., 'D:', 'C:'
            # If the drive is connected, show green, else red
            if self.is_drive_connected(drive):
                self.drive_status_labels[name].config(text="🟢")
            else:
                self.drive_status_labels[name].config(text="🔴")

        # schedule next check
        self.root.after(self.drive_check_interval, self.check_drives)

    def is_drive_connected(self, drive):
        try:
            shutil.disk_usage(drive + os.sep)
            return True
        except:
            return False

    # ------------------ Podcasts Management Methods ------------------
    def open_add_podcast_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Add Podcast")
        dialog.geometry("400x200+150+100")
        dialog.resizable(False, False)

        name_var = tk.StringVar()
        url_var = tk.StringVar()
        output_var = tk.StringVar()

        ttk.Label(dialog, text="Podcast Name:").pack(pady=2, padx=10, anchor="w")
        ttk.Entry(dialog, textvariable=name_var, width=50).pack(pady=2, padx=10)

        ttk.Label(dialog, text="RSS Feed URL:").pack(pady=2, padx=10, anchor="w")
        ttk.Entry(dialog, textvariable=url_var, width=50).pack(pady=2, padx=10)

        def choose_output():
            path = filedialog.askdirectory(title="Select Output Directory")
            if path:
                output_var.set(path)

        folder_frame = ttk.Frame(dialog)
        folder_frame.pack(pady=2, padx=10, fill="x")
        ttk.Label(folder_frame, text="Output Folder:").pack(side="left")
        ttk.Entry(folder_frame, textvariable=output_var, width=35).pack(
            side="left", padx=3
        )
        ttk.Button(folder_frame, text="Browse", command=choose_output).pack(side="left")

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)

        def on_ok():
            n = name_var.get().strip()
            u = url_var.get().strip()
            o = output_var.get().strip()
            if n and u and o:
                self.config[n] = {"url": u, "output": o}
                self.podcasts[n] = {"url": u, "output": o}
                self.save_config()
                self.refresh_list()
            dialog.destroy()

        ttk.Button(btn_frame, text="OK", command=on_ok).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(
            side="left", padx=5
        )
        dialog.wait_window(dialog)

    def open_edit_podcast_dialog(self, podcast_name):
        dialog = tk.Toplevel(self.root)
        dialog.title("Edit Podcast")
        dialog.geometry("400x200+150+100")
        dialog.resizable(False, False)

        current_url = self.podcasts[podcast_name]["url"]
        current_output = self.podcasts[podcast_name]["output"]
        url_var = tk.StringVar(value=current_url)
        output_var = tk.StringVar(value=current_output)

        ttk.Label(dialog, text="RSS Feed URL:").pack(pady=2, padx=10, anchor="w")
        ttk.Entry(dialog, textvariable=url_var, width=50).pack(pady=2, padx=10)

        def choose_output():
            path = filedialog.askdirectory(title="Select Output Directory")
            if path:
                output_var.set(path)

        folder_frame = ttk.Frame(dialog)
        folder_frame.pack(pady=2, padx=10, fill="x")
        ttk.Label(folder_frame, text="Output Folder:").pack(side="left")
        ttk.Entry(folder_frame, textvariable=output_var, width=35).pack(
            side="left", padx=3
        )
        ttk.Button(folder_frame, text="Browse", command=choose_output).pack(side="left")

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)

        def on_ok():
            u = url_var.get().strip()
            o = output_var.get().strip()
            if u and o:
                self.config[podcast_name]["url"] = u
                self.config[podcast_name]["output"] = o
                self.podcasts[podcast_name] = {"url": u, "output": o}
                self.save_config()
                self.refresh_list()
            dialog.destroy()

        ttk.Button(btn_frame, text="OK", command=on_ok).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(
            side="left", padx=5
        )
        dialog.wait_window(dialog)

    def add_podcast(self):
        self.open_add_podcast_dialog()

    def edit_podcast(self):
        selected = [name for name, var in self.check_vars.items() if var.get()]
        if len(selected) != 1:
            messagebox.showinfo("Edit Podcast", "Select exactly one podcast to edit.")
            return
        self.open_edit_podcast_dialog(selected[0])

    def remove_podcast(self):
        selected = [name for name, var in self.check_vars.items() if var.get()]
        if not selected:
            messagebox.showinfo(
                "Remove Podcast", "Select at least one podcast to remove."
            )
            return
        for name in selected:
            self.config.remove_section(name)
            del self.podcasts[name]
        self.save_config()
        self.refresh_list()

    # ------------------ Podcasts Update & Others ------------------
    def update_selected(self):
        """Download updates only for podcasts that are checked/selected."""
        selected = [name for name, var in self.check_vars.items() if var.get()]
        if not selected:
            messagebox.showinfo("Update", "Select at least one podcast.")
            return
        self.stop_flag = False
        threading.Thread(
            target=self.update_podcasts, args=(selected,), daemon=True
        ).start()

    def update_podcasts(self, podcast_names):
        try:
            max_episodes = (
                int(self.max_episodes_var.get())
                if self.max_episodes_var.get().isdigit()
                else None
            )
        except:
            max_episodes = None

        filter_date = None
        if self.filter_date_var.get():
            try:
                filter_date = datetime.datetime.strptime(
                    self.filter_date_var.get(), "%Y-%m-%d"
                )
            except:
                self.log("Invalid filter date format. Ignoring date filter.")

        tasks = []
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

        self.root.after(
            0, lambda: self.progress_bar.config(maximum=total_tasks, value=0)
        )

        for podcast_name, enc, output in tasks:
            file_url = enc.href
            filename = os.path.basename(file_url.split("?")[0])
            filepath = os.path.join(output, filename)

            if os.path.exists(filepath):
                try:
                    existing_size = os.path.getsize(filepath)
                    if existing_size > 10 * 1024 * 1024:
                        self.log(f"Skipping existing file over 10MB: {filename}")
                        self.root.after(0, lambda: self.progress_bar.step(1))
                        if self.stop_flag:
                            self.log("Stopping after current download.")
                            break
                        continue
                except Exception as e:
                    self.log(
                        f"Error checking existing file: {filename}, proceeding to download. Error: {e}"
                    )

            self.log(f"Downloading file for '{podcast_name}'...")
            try:
                with requests.get(file_url, stream=True, timeout=10) as r:
                    r.raise_for_status()
                    os.makedirs(output, exist_ok=True)

                    with open(filepath, "wb") as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                # Minimal text update
                                progress_text = "Keeping it real."
                                self.root.after(
                                    0,
                                    lambda text=progress_text: self.file_progress_label.config(
                                        text=text
                                    ),
                                )
                self.log(f"Downloaded: {filename}")
            except Exception as e:
                self.log(f"Error downloading {filename}: {e}")

            self.root.after(0, lambda: self.progress_bar.step(1))

            if self.stop_flag:
                self.log("Stopping after current download.")
                break

        self.log("Update completed.")
        self.root.after(0, self.show_storage)

    def download_one_off(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("One-Off Download")
        dialog.geometry("400x150+150+100")
        dialog.resizable(False, False)

        url_var = tk.StringVar()
        output_var = tk.StringVar()

        ttk.Label(dialog, text="RSS Feed URL:").pack(pady=2, padx=10, anchor="w")
        ttk.Entry(dialog, textvariable=url_var, width=50).pack(pady=2, padx=10)

        def choose_output():
            path = filedialog.askdirectory(title="Select Output Directory")
            if path:
                output_var.set(path)

        folder_frame = ttk.Frame(dialog)
        folder_frame.pack(pady=2, padx=10, fill="x")
        ttk.Label(folder_frame, text="Output Folder:").pack(side="left")
        ttk.Entry(folder_frame, textvariable=output_var, width=35).pack(
            side="left", padx=3
        )
        ttk.Button(folder_frame, text="Browse", command=choose_output).pack(side="left")

        def on_ok():
            u = url_var.get().strip()
            o = output_var.get().strip()
            if u and o:
                threading.Thread(
                    target=self._one_off_task, args=(u, o), daemon=True
                ).start()
            dialog.destroy()

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="OK", command=on_ok).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(
            side="left", padx=5
        )
        dialog.wait_window(dialog)

    def _one_off_task(self, url, output):
        feed = feedparser.parse(url)
        if not feed.entries:
            self.root.after(
                0, lambda: messagebox.showinfo("Error", "No entries found.")
            )
            return

        entry = feed.entries[0]
        if "enclosures" in entry:
            enc = entry.enclosures[0]
            file_url = enc.href
            filename = os.path.basename(file_url.split("?")[0])
            filepath = os.path.join(output, filename)

            try:
                with requests.get(file_url, stream=True, timeout=10) as r:
                    r.raise_for_status()
                    with open(filepath, "wb") as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                self.root.after(
                    0, lambda: messagebox.showinfo("Success", f"Downloaded: {filename}")
                )
            except Exception as e:
                self.root.after(0, lambda: messagebox.showinfo("Error", str(e)))

    def set_stop_flag(self):
        self.stop_flag = True
        self.log("Stop flag set.")

    def switch_user(self):
        if messagebox.askyesno("Switch User", "Are you sure you want to switch user?"):
            self.switch_user_requested = True
            self.root.destroy()

    def log(self, message):
        print(message)

        def update_ui():
            self.progress_label.config(text=message)
            if hasattr(self, "log_text"):
                self.log_text.insert("end", message + "\n")
                self.log_text.see("end")

        self.root.after(0, update_ui)

    def filter_entries(self, entries, max_episodes, filter_date):
        filtered = []
        for entry in entries:
            if filter_date:
                if "published_parsed" in entry and entry.published_parsed:
                    entry_date = datetime.datetime(*entry.published_parsed[:6])
                    if entry_date < filter_date:
                        continue
            filtered.append(entry)
        if max_episodes is not None:
            filtered = filtered[:max_episodes]
        return filtered


if __name__ == "__main__":
    while True:
        root = tk.Tk()
        app = PodcastManagerApp(root, "admin")
        root.mainloop()
        if not app.switch_user_requested:
            break
