import os
import configparser
import shutil
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import feedparser
import requests
import datetime

# For pie charts in the Storage tab
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

# -----------------------
# ICONS (base64 encoded PNGs)
# Dummy 16x16 icons for demonstration.
ICON_ADD = """
iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAIAAACQkWg2AAAADUlEQVR42mP8z/C/HwAFgwJ/lSV38AAAAABJRU5ErkJggg==
"""
ICON_EDIT = """
iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAIAAACQkWg2AAAADklEQVR42mP8/5+hHgAFAAL/7aK+7QAAAABJRU5ErkJggg==
"""
ICON_REMOVE = """
iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAIAAACQkWg2AAAADUlEQVR42mNk+M+gHgAFAgJ/5r1F1wAAAABJRU5ErkJggg==
"""
ICON_DOWNLOAD = """
iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAIAAACQkWg2AAAADklEQVR42mP8/5+hHgAFGwJ/lKcJ1wAAAABJRU5ErkJggg==
"""

CONFIG_PATH = r'C:\tools\config\pods.ini'
DEFAULT_TOLERANCE_MB = 5

def format_bytes(num_bytes):
    """Return a human-friendly string for bytes (in GB or MB)."""
    if num_bytes >= 1024**3:
        return f"{num_bytes/1024**3:.2f} GB"
    elif num_bytes >= 1024**2:
        return f"{num_bytes/1024**2:.2f} MB"
    elif num_bytes >= 1024:
        return f"{num_bytes/1024:.2f} KB"
    else:
        return f"{num_bytes} B"

class PodcastManagerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Podcast Manager")
        self.root.geometry("800x600")

        # Use a modern ttk theme if available
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        # Attempt to load icons
        try:
            self.icon_add = tk.PhotoImage(data=ICON_ADD.strip())
            self.icon_edit = tk.PhotoImage(data=ICON_EDIT.strip())
            self.icon_remove = tk.PhotoImage(data=ICON_REMOVE.strip())
            self.icon_download = tk.PhotoImage(data=ICON_DOWNLOAD.strip())
        except Exception:
            self.icon_add = self.icon_edit = self.icon_remove = self.icon_download = None

        self.podcasts = {}
        self.check_vars = {}

        self.ensure_config()
        self.load_config()
        self.build_gui()

    def ensure_config(self):
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        if not os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'w') as f:
                f.write('')

    def load_config(self):
        self.config = configparser.ConfigParser()
        self.config.read(CONFIG_PATH)
        for section in self.config.sections():
            self.podcasts[section] = {
                'url': self.config[section]['url'],
                'output': self.config[section]['output']
            }

    def save_config(self):
        with open(CONFIG_PATH, 'w') as configfile:
            self.config.write(configfile)

    def build_gui(self):
        # Notebook with two tabs: Podcasts and Storage
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

        # Bottom Frame for integrated progress info
        bottom_frame = ttk.Frame(self.root)
        bottom_frame.pack(side="bottom", fill="x")

        self.progress_label = ttk.Label(bottom_frame, text="Ready")
        self.progress_label.pack(side="left", padx=10)

        self.progress_bar = ttk.Progressbar(bottom_frame, length=300, mode='determinate')
        self.progress_bar.pack(side="left", padx=10, pady=5)

    # --------------------------------------------------------------------------
    # Podcast Tab
    def build_podcast_tab(self, parent):
        top_frame = ttk.Frame(parent)
        top_frame.pack(fill="x", pady=5, padx=5)

        # Buttons with icons if available
        btn_opts = {"compound": tk.LEFT} if self.icon_add else {}
        ttk.Button(top_frame, text=" Add", image=self.icon_add, **btn_opts, command=self.add_podcast).pack(side="left", padx=3)
        ttk.Button(top_frame, text=" Edit", image=self.icon_edit, **btn_opts, command=self.edit_podcast).pack(side="left", padx=3)
        ttk.Button(top_frame, text=" Remove", image=self.icon_remove, **btn_opts, command=self.remove_podcast).pack(side="left", padx=3)
        ttk.Button(top_frame, text=" Download One-Off", image=self.icon_download, **btn_opts, command=self.download_one_off).pack(side="left", padx=3)

        # Tolerance setting
        tol_frame = ttk.Frame(parent)
        tol_frame.pack(fill="x", padx=5, pady=5)
        ttk.Label(tol_frame, text="Tolerance (MB):").pack(side="left")
        self.tolerance_var = tk.StringVar(value=str(DEFAULT_TOLERANCE_MB))
        ttk.Entry(tol_frame, textvariable=self.tolerance_var, width=5).pack(side="left", padx=3)

        # Update buttons
        update_frame = ttk.Frame(parent)
        update_frame.pack(fill="x", padx=5, pady=5)
        ttk.Button(update_frame, text="Update Selected", command=self.update_selected).pack(side="left", padx=3)
        ttk.Button(update_frame, text="Update All", command=self.update_all).pack(side="left", padx=3)

        # Podcast List (scrollable frame)
        list_frame = ttk.Frame(parent)
        list_frame.pack(fill="both", expand=True, padx=5, pady=5)

        canvas = tk.Canvas(list_frame)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        self.podcast_list_frame = ttk.Frame(canvas)

        self.podcast_list_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self.podcast_list_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.refresh_list()

    def refresh_list(self):
        for widget in self.podcast_list_frame.winfo_children():
            widget.destroy()
        self.check_vars = {}
        for idx, (name, data) in enumerate(self.podcasts.items()):
            var = tk.BooleanVar()
            chk = ttk.Checkbutton(
                self.podcast_list_frame,
                text=f"{name} | {data['url']} | {data['output']}",
                variable=var
            )
            chk.grid(row=idx, column=0, sticky="w", padx=2, pady=2)
            self.check_vars[name] = var

    # --------------------------------------------------------------------------
    # Storage Tab
    def build_storage_tab(self, parent):
        ttk.Button(parent, text="Refresh Storage Info", command=self.show_storage).pack(pady=5)
        self.storage_chart_frame = ttk.Frame(parent)
        self.storage_chart_frame.pack(fill="both", expand=True)
        self.show_storage()

    def show_storage(self):
        # Clear previous widgets in storage_chart_frame
        for widget in self.storage_chart_frame.winfo_children():
            widget.destroy()

        # Gather drives from podcast outputs
        drives = {}
        for data in self.podcasts.values():
            drive = os.path.splitdrive(data['output'])[0]
            if drive not in drives:
                try:
                    total, used, free = shutil.disk_usage(drive + os.sep)
                    drives[drive] = (total, used, free)
                except Exception:
                    drives[drive] = (0, 0, 0)

        # Create a figure for the drives
        num_drives = len(drives)
        fig = Figure(figsize=(6, 4*num_drives if num_drives > 0 else 4), dpi=100)

        if num_drives > 0:
            axs = fig.subplots(num_drives, 1) if num_drives > 1 else [fig.add_subplot(111)]
        else:
            axs = [fig.add_subplot(111)]
            axs[0].text(0.5, 0.5, "No drives found", ha='center')

        for ax, (drive, (total, used, free)) in zip(axs, drives.items()):
            # Calculate percentages
            used_pct = used / total * 100 if total > 0 else 0
            free_pct = free / total * 100 if total > 0 else 0
            # Draw pie chart
            wedges, texts, autotexts = ax.pie(
                [used_pct, free_pct],
                labels=[f"Used ({used_pct:.1f}%)", f"Free ({free_pct:.1f}%)"],
                autopct="%1.1f%%",
                startangle=90
            )
            ax.set_title(f"Drive {drive}")
            # Annotate with detailed statistics below the pie chart
            stats_text = (
                f"Total: {format_bytes(total)}\n"
                f"Used: {format_bytes(used)}\n"
                f"Free: {format_bytes(free)}"
            )
            ax.text(0.5, -0.15, stats_text, transform=ax.transAxes, ha="center", va="top", fontsize=10)
        fig.tight_layout()

        canvas = FigureCanvasTkAgg(fig, master=self.storage_chart_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)

    # --------------------------------------------------------------------------
    # Custom Dialogs for Add/Edit Podcast
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
        ttk.Entry(folder_frame, textvariable=output_var, width=35).pack(side="left", padx=3)
        ttk.Button(folder_frame, text="Browse", command=choose_output).pack(side="left")

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)
        def on_ok():
            n = name_var.get().strip()
            u = url_var.get().strip()
            o = output_var.get().strip()
            if n and u and o:
                self.config[n] = {'url': u, 'output': o}
                self.podcasts[n] = {'url': u, 'output': o}
                self.save_config()
                self.refresh_list()
                self.show_storage()
            dialog.destroy()
        ttk.Button(btn_frame, text="OK", command=on_ok).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side="left", padx=5)
        dialog.wait_window(dialog)

    def open_edit_podcast_dialog(self, podcast_name):
        dialog = tk.Toplevel(self.root)
        dialog.title("Edit Podcast")
        dialog.geometry("400x200+150+100")
        dialog.resizable(False, False)

        current_url = self.podcasts[podcast_name]['url']
        current_output = self.podcasts[podcast_name]['output']
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
        ttk.Entry(folder_frame, textvariable=output_var, width=35).pack(side="left", padx=3)
        ttk.Button(folder_frame, text="Browse", command=choose_output).pack(side="left")

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)
        def on_ok():
            u = url_var.get().strip()
            o = output_var.get().strip()
            if u and o:
                self.config[podcast_name]['url'] = u
                self.config[podcast_name]['output'] = o
                self.podcasts[podcast_name] = {'url': u, 'output': o}
                self.save_config()
                self.refresh_list()
                self.show_storage()
            dialog.destroy()
        ttk.Button(btn_frame, text="OK", command=on_ok).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side="left", padx=5)
        dialog.wait_window(dialog)

    # --------------------------------------------------------------------------
    # Podcast Management
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
            messagebox.showinfo("Remove Podcast", "Select at least one podcast to remove.")
            return
        for name in selected:
            self.config.remove_section(name)
            del self.podcasts[name]
        self.save_config()
        self.refresh_list()
        self.show_storage()

    # --------------------------------------------------------------------------
    # Updating
    def update_selected(self):
        selected = [name for name, var in self.check_vars.items() if var.get()]
        if not selected:
            messagebox.showinfo("Update", "Select at least one podcast.")
            return
        threading.Thread(target=self.update_podcasts, args=(selected,), daemon=True).start()

    def update_all(self):
        threading.Thread(target=self.update_podcasts, args=(list(self.podcasts.keys()),), daemon=True).start()

    def update_podcasts(self, podcast_names):
        try:
            max_episodes = int(self.max_episodes_var.get()) if self.max_episodes_var.get().isdigit() else None
        except:
            max_episodes = None

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
        self.progress["maximum"] = total_tasks
        self.progress["value"] = 0

        # Process each download task
        for podcast_name, enc, output in tasks:
            file_url = enc.href
            filename = os.path.basename(file_url.split("?")[0])
            filepath = os.path.join(output, filename)
            if os.path.exists(filepath):
                try:
                    existing_size = os.path.getsize(filepath)
                    if existing_size > 10 * 1024 * 1024:  # Skip files larger than 10MB
                        self.log(f"Skipping existing file over 10MB: {filename}")
                        self.progress["value"] += 1
                        continue
                except Exception as e:
                    self.log(f"Error checking existing file: {filename}, proceeding to download. Error: {e}")

            self.log(f"Downloading {filename} from '{podcast_name}'...")
            try:
                with requests.get(file_url, stream=True, timeout=10) as r:
                    r.raise_for_status()
                    os.makedirs(output, exist_ok=True)
                    with open(filepath, "wb") as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                self.log(f"Downloaded: {filename}")
            except Exception as e:
                self.log(f"Error downloading {filename}: {e}")
            self.progress["value"] += 1

        self.log("Update completed.")
        self.update_storage_info()

    def _start_progress(self, total):
        self.progress_bar["maximum"] = total
        self.progress_bar["value"] = 0
        self.progress_label["text"] = "Starting updates..."

    def _update_progress(self, count, message):
        self.progress_bar["value"] = count
        self.progress_label["text"] = message
        self.root.update_idletasks()

    def _finish_progress(self):
        self.progress_label["text"] = "All downloads complete."
        self.root.update_idletasks()

    # --------------------------------------------------------------------------
    # One-Off Download
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
        ttk.Entry(folder_frame, textvariable=output_var, width=35).pack(side="left", padx=3)
        ttk.Button(folder_frame, text="Browse", command=choose_output).pack(side="left")

        def on_ok():
            u = url_var.get().strip()
            o = output_var.get().strip()
            if u and o:
                threading.Thread(target=self._one_off_task, args=(u, o), daemon=True).start()
            dialog.destroy()
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="OK", command=on_ok).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side="left", padx=5)
        dialog.wait_window(dialog)

    def _one_off_task(self, url, output):
        feed = feedparser.parse(url)
        if not feed.entries:
            self.root.after(0, lambda: messagebox.showinfo("Error", "No entries found."))
            return
        entry = feed.entries[0]
        if 'enclosures' in entry:
            enc = entry.enclosures[0]
            file_url = enc.href
            filename = os.path.basename(file_url.split("?")[0])
            filepath = os.path.join(output, filename)
            try:
                with requests.get(file_url, stream=True, timeout=10) as r:
                    r.raise_for_status()
                    with open(filepath, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                self.root.after(0, lambda: messagebox.showinfo("Success", f"Downloaded: {filename}"))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showinfo("Error", str(e)))

# ------------------------------------------------------------------------------
if __name__ == '__main__':
    root = tk.Tk()
    app = PodcastManagerApp(root)
    root.mainloop()
