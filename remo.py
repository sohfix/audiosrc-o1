#!/usr/bin/env python3
import os
import sys
import shutil
import configparser
import logging
import tkinter as tk
from tkinter import messagebox, filedialog, ttk
import datetime
import threading
import psutil  # dependency for system monitoring/cleanup

# -----------------------------------------
#  Constants & Paths
# -----------------------------------------
DIRK = r"C:\audiosrc-o1"
BASE_DIR = os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__))
INI_PATH = os.path.join(BASE_DIR, "remo.ini")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
BANNER_PATH = os.path.join(DIRK, "REMO_BANNER.png")
ICON_PATH = os.path.join(BASE_DIR, "remo_icon.ico")

# -----------------------------------------
#  Global Config / Logging
# -----------------------------------------
config = configparser.ConfigParser()

def setup_logging():
    os.makedirs(LOGS_DIR, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(LOGS_DIR, f"remo_{timestamp}.log")
    logging.basicConfig(filename=log_file, level=logging.INFO,
                        format="%(asctime)s - %(levelname)s - %(message)s")
    logging.info("Logging initialized.")

def load_config():
    """Load config from remo.ini, create default if missing."""
    if not os.path.exists(INI_PATH):
        create_default_config()
    config.read(INI_PATH)
    if "Settings" not in config:
        config["Settings"] = {}
    if "Directories" not in config:
        config["Directories"] = {}
    config["Settings"].setdefault("dark_mode", "true")
    config["Directories"].setdefault("paths", "")
    save_config()

def create_default_config():
    """Create a brand‐new config with default values."""
    config["Settings"] = {"dark_mode": "true"}
    config["Directories"] = {"paths": ""}
    save_config()

def save_config():
    """Write current config state to file."""
    with open(INI_PATH, "w") as f:
        config.write(f)
    logging.info("Config saved.")

# -----------------------------------------
#  Helper Functions for Size Calculation
# -----------------------------------------
def get_directory_size(path):
    total = 0
    for root, dirs, files in os.walk(path):
        for file in files:
            try:
                total += os.path.getsize(os.path.join(root, file))
            except Exception:
                pass
    return total

def human_readable(num, suffix="B"):
    for unit in ["", "K", "M", "G", "T", "P"]:
        if abs(num) < 1024.0:
            return f"{num:.2f}{unit}{suffix}"
        num /= 1024.0
    return f"{num:.2f}Y{suffix}"

# -----------------------------------------
#  Cleanup Functions with Progress Callback
# -----------------------------------------
def remove_path(path, progress_callback=None):
    """Delete a file or folder (recursively) and report removed size."""
    try:
        removed_size = 0
        if os.path.isdir(path):
            removed_size = get_directory_size(path)
            shutil.rmtree(path)
            msg = f"Removed directory: {path} ({human_readable(removed_size)})"
        elif os.path.exists(path):
            removed_size = os.path.getsize(path)
            os.remove(path)
            msg = f"Removed file: {path} ({human_readable(removed_size)})"
        else:
            msg = f"Path not found: {path}"
        if progress_callback:
            progress_callback(msg, removed_size)
        logging.info(msg)
        return msg, removed_size
    except Exception as e:
        msg = f"Error removing {path}: {e}"
        logging.error(msg)
        if progress_callback:
            progress_callback(msg, 0)
        return msg, 0

def move_exe_from_dist(base, progress_callback=None):
    """Move .exe files from the 'dist' folder in `base` to `base` itself."""
    summary = []
    dist = os.path.join(base, "dist")
    if not os.path.isdir(dist):
        return ["No 'dist' folder."]
    found_any = False
    for f in os.listdir(dist):
        if f.lower().endswith(".exe"):
            found_any = True
            src = os.path.join(dist, f)
            dst = os.path.join(base, f)
            try:
                shutil.move(src, dst)
                msg = f"Moved {f} to {base}"
                summary.append(msg)
                if progress_callback:
                    progress_callback(msg, 0)
            except Exception as e:
                msg = f"Failed to move {f}: {e}"
                summary.append(msg)
                if progress_callback:
                    progress_callback(msg, 0)
    if not found_any:
        summary.append("No .exe files in 'dist'.")
    return summary

def remove_spec_files(directory, progress_callback=None):
    """Remove .spec files in `directory`."""
    summary = []
    for f in os.listdir(directory):
        if f.lower().endswith(".spec"):
            full_path = os.path.join(directory, f)
            msg, size = remove_path(full_path, progress_callback)
            summary.append(msg)
    return summary

def remove_pycache_dirs(directory, progress_callback=None):
    """Remove __pycache__ dirs under `directory`, recursively."""
    summary = []
    for root, dirs, _ in os.walk(directory):
        for d in dirs:
            if d == "__pycache__":
                full_path = os.path.join(root, d)
                msg, size = remove_path(full_path, progress_callback)
                summary.append(msg)
    return summary

def process_directory(path, progress_callback=None):
    """Perform the standard cleanup steps on one directory."""
    total_removed = 0
    messages = [f"Processing: {path}"]
    if not os.path.isdir(path):
        msg = f"Not a valid directory: {path}"
        messages.append(msg)
        if progress_callback:
            progress_callback(msg, 0)
        return messages, total_removed

    # 1) Move exe from dist (no size change here)
    msgs = move_exe_from_dist(path, progress_callback)
    messages += msgs

    # 2) Remove build folder
    msg, size = remove_path(os.path.join(path, "build"), progress_callback)
    messages.append(msg)
    total_removed += size

    # 3) Remove dist folder
    msg, size = remove_path(os.path.join(path, "dist"), progress_callback)
    messages.append(msg)
    total_removed += size

    # 4) Remove .spec files
    msgs = remove_spec_files(path, progress_callback)
    messages += msgs

    # 5) Remove __pycache__ directories
    msgs = remove_pycache_dirs(path, progress_callback)
    messages += msgs

    messages.append("-" * 40)
    return messages, total_removed

def perform_cleanup(progress_callback=None):
    """Cleanup all directories from config and return overall messages and total bytes cleaned."""
    total_cleaned = 0
    dir_list = get_tracked_folders()
    messages = []
    if not dir_list:
        msg = "No directories to process."
        messages.append(msg)
        if progress_callback:
            progress_callback(msg, 0)
        return "\n".join(messages), total_cleaned
    for d in dir_list:
        msgs, removed = process_directory(d, progress_callback)
        messages += msgs
        total_cleaned += removed
    return "\n".join(messages), total_cleaned

def clean_system_cache(progress_callback=None):
    """Clean common system cache directories."""
    total_removed = 0
    messages = []
    cache_dirs = [
        os.environ.get("TEMP", r"C:\Windows\Temp"),
        os.path.join(os.environ.get("LOCALAPPDATA", r"C:\Users\Public\AppData"), "Temp")
    ]
    for d in cache_dirs:
        msg, size = remove_path(d, progress_callback)
        messages.append(msg)
        total_removed += size
    return "\n".join(messages), total_removed

def clean_external_drives(progress_callback=None):
    """Clean temporary files on external (removable) drives."""
    total_removed = 0
    messages = []
    for part in psutil.disk_partitions():
        if 'removable' in part.opts.lower():
            drive = part.mountpoint
            temp_path = os.path.join(drive, "Temp")
            msg, size = remove_path(temp_path, progress_callback)
            messages.append(f"Cleaning drive {drive}: {msg}")
            total_removed += size
    return "\n".join(messages), total_removed

# -----------------------------------------
#  Activity Monitor (Dashboard)
# -----------------------------------------
class ActivityMonitor(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.cpu_label = ttk.Label(self, text="CPU Usage: ")
        self.cpu_label.pack(anchor="w", padx=5, pady=2)
        self.mem_label = ttk.Label(self, text="Memory Usage: ")
        self.mem_label.pack(anchor="w", padx=5, pady=2)
        self.disk_label = ttk.Label(self, text="Disk Usage: ")
        self.disk_label.pack(anchor="w", padx=5, pady=2)
        self.update_stats()

    def update_stats(self):
        cpu = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory().percent
        disk = psutil.disk_usage(os.environ.get("SystemDrive", "C:\\")).percent
        self.cpu_label.config(text=f"CPU Usage: {cpu}%")
        self.mem_label.config(text=f"Memory Usage: {mem}%")
        self.disk_label.config(text=f"Disk Usage: {disk}%")
        self.after(1000, self.update_stats)

# -----------------------------------------
#  Directory List Helpers
# -----------------------------------------
def get_tracked_folders():
    raw = config["Directories"].get("paths", "")
    return [p.strip() for p in raw.split(";") if p.strip()]

def set_tracked_folders(folder_list):
    joined = "; ".join(folder_list)
    config["Directories"]["paths"] = joined
    save_config()

def add_directory_to_ini(path):
    dirs = get_tracked_folders()
    if path not in dirs:
        dirs.append(path)
        set_tracked_folders(dirs)
        logging.info(f"Added to config: {path}")
        return f"Added: {path}"
    return "Already exists."

def remove_directory_from_ini(path):
    dirs = get_tracked_folders()
    if path in dirs:
        dirs.remove(path)
        set_tracked_folders(dirs)
        logging.info(f"Removed from config: {path}")
        return f"Removed: {path}"
    return "Not found in list."

# -----------------------------------------
#  Cleanup Progress Window (with stats)
# -----------------------------------------
class CleanupProgressWindow(tk.Toplevel):
    """Window showing a progress bar plus cleanup messages and total data removed."""
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Cleaning in Progress...")
        self.geometry("400x300")
        self.resizable(False, False)
        self.total_removed = 0

        # Banner (if available)
        if os.path.exists(BANNER_PATH):
            try:
                self.banner = tk.PhotoImage(file=BANNER_PATH)
                tk.Label(self, image=self.banner).pack()
            except Exception:
                pass

        self.progress_label = ttk.Label(self, text="Total Cleaned: 0B")
        self.progress_label.pack(pady=5)

        self.progress_bar = ttk.Progressbar(self, mode="indeterminate")
        self.progress_bar.pack(fill=tk.X, padx=20, pady=5)
        self.progress_bar.start()

        self.log_text = tk.Text(self, height=10, wrap="word")
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    def update_progress(self, message, bytes_removed):
        # Update total
        self.total_removed += bytes_removed
        self.progress_label.config(text=f"Total Cleaned: {human_readable(self.total_removed)}")
        # Append message
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)

# -----------------------------------------
#  Main Application
# -----------------------------------------
class RemoApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("REMO Cl")
        self.geometry("700x500")
        self.dark_mode = (config["Settings"].get("dark_mode", "true").lower() == "true")
        self.apply_dark_mode_style()
        self.load_icon()
        self.banner_image = None

        self.create_menubar()
        self.create_main_widgets()
        self.log("REMO Cleaner with System Tools and Detailed Progress")

    def load_icon(self):
        if os.path.exists(ICON_PATH):
            try:
                self.iconbitmap(ICON_PATH)
            except Exception as e:
                logging.error(f"Error loading icon: {e}")

    def create_menubar(self):
        menubar = tk.Menu(self)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Exit", command=self.safe_exit)
        menubar.add_cascade(label="File", menu=file_menu)
        settings_menu = tk.Menu(menubar, tearoff=0)
        settings_menu.add_command(label="Open Settings...", command=self.open_settings_window)
        settings_menu.add_command(label="Toggle Dark Mode", command=self.toggle_dark_mode)
        menubar.add_cascade(label="Settings", menu=settings_menu)
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="About", command=self.show_about)
        help_menu.add_command(label="Check for Updates", command=self.check_updates)
        menubar.add_cascade(label="Help", menu=help_menu)
        self.config(menu=menubar)

    def create_main_widgets(self):
        if os.path.exists(BANNER_PATH):
            try:
                self.banner_image = tk.PhotoImage(file=BANNER_PATH)
                tk.Label(self, image=self.banner_image, bg=self["bg"]).pack(pady=5)
            except Exception as e:
                logging.error(f"Error loading banner: {e}")
        frame = ttk.Frame(self)
        frame.pack(pady=10)
        ttk.Button(frame, text="Start Cleanup", command=self.start_cleanup).grid(row=0, column=0, padx=10)
        ttk.Button(frame, text="Exit", command=self.safe_exit).grid(row=0, column=1, padx=10)
        self.log_box = tk.Text(self, height=12, wrap="word")
        self.log_box.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.log_box.insert(tk.END, "REMO ready.\n")

    def start_cleanup(self):
        self.log("🧹 Starting cleanup...")
        prog_win = CleanupProgressWindow(self)

        def progress_callback(message, bytes_removed):
            self.after(0, lambda: prog_win.update_progress(message, bytes_removed))

        def worker():
            std_msg, std_removed = perform_cleanup(progress_callback)
            sys_msg, sys_removed = clean_system_cache(progress_callback)
            ext_msg, ext_removed = clean_external_drives(progress_callback)
            combined = "\n".join([std_msg, sys_msg, ext_msg])
            prog_win.progress_bar.stop()
            self.after(0, prog_win.destroy)
            self.log(combined)
            total = std_removed + sys_removed + ext_removed
            self.log(f"Total cleaned: {human_readable(total)}")
        threading.Thread(target=worker, daemon=True).start()

    def apply_dark_mode_style(self):
        if self.dark_mode:
            self.configure(bg="#1f1f1f")
        else:
            self.configure(bg="#f0f0f0")

    def toggle_dark_mode(self):
        self.dark_mode = not self.dark_mode
        config["Settings"]["dark_mode"] = "true" if self.dark_mode else "false"
        save_config()
        self.apply_dark_mode_style()
        self.log(f"Dark mode = {self.dark_mode}")

    def log(self, msg):
        self.log_box.insert(tk.END, msg + "\n")
        self.log_box.see(tk.END)
        logging.info(msg)

    def show_about(self):
        messagebox.showinfo("About", "REMO Cleaner with System Tools and Detailed Progress")

    def check_updates(self):
        messagebox.showinfo("Check Updates", "No updates available at this time.")

    def safe_exit(self):
        self.destroy()
        self.quit()

    def open_settings_window(self):
        SettingsWindow(self, self.dark_mode)

# -----------------------------------------
#  Settings Window (Notebook with tabs)
# -----------------------------------------
class SettingsWindow(tk.Toplevel):
    def __init__(self, parent, dark_mode):
        super().__init__(parent)
        self.parent = parent
        self.dark_mode = dark_mode
        self.title("Settings")
        self.geometry("600x400")
        self.configure(bg=parent["bg"])
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # General Tab
        self.tab_general = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_general, text="General")
        self.build_general_tab()

        # Folders Tab
        self.tab_folders = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_folders, text="Folders")
        self.build_folders_tab()

        # System Cleaner Tab
        self.tab_system = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_system, text="System Cleaner")
        self.build_system_tab()

        # Activity Monitor Tab
        self.tab_monitor = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_monitor, text="Activity Monitor")
        self.build_monitor_tab()

    def build_general_tab(self):
        frame = ttk.Frame(self.tab_general)
        frame.pack(fill=tk.BOTH, expand=True, pady=10, padx=10)
        self.dark_var = tk.BooleanVar(value=self.dark_mode)
        dark_check = ttk.Checkbutton(frame, text="Use Dark Mode", variable=self.dark_var)
        dark_check.pack(anchor="w", pady=5)
        ttk.Button(frame, text="Save", command=self.save_general_settings).pack(side="right", padx=5, pady=5)

    def save_general_settings(self):
        config["Settings"]["dark_mode"] = "true" if self.dark_var.get() else "false"
        save_config()
        self.parent.dark_mode = self.dark_var.get()
        self.parent.apply_dark_mode_style()
        self.parent.log("General settings saved.")

    def build_folders_tab(self):
        frame = ttk.Frame(self.tab_folders)
        frame.pack(fill=tk.BOTH, expand=True, pady=10, padx=10)
        self.folder_listbox = tk.Listbox(frame, selectmode=tk.SINGLE, height=8)
        self.folder_listbox.pack(fill=tk.BOTH, expand=True, side="left")
        for d in get_tracked_folders():
            self.folder_listbox.insert(tk.END, d)
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(side="right", fill=tk.Y, padx=5)
        ttk.Button(btn_frame, text="Add...", command=self.add_folder).pack(pady=2)
        ttk.Button(btn_frame, text="Remove", command=self.remove_folder).pack(pady=2)
        ttk.Button(btn_frame, text="Save", command=self.save_folder_list).pack(pady=(20,2))

    def add_folder(self):
        path = filedialog.askdirectory(title="Select Folder to Add")
        if path:
            self.folder_listbox.insert(tk.END, path)

    def remove_folder(self):
        sel = self.folder_listbox.curselection()
        if sel:
            self.folder_listbox.delete(sel[0])

    def save_folder_list(self):
        folders = [self.folder_listbox.get(i) for i in range(self.folder_listbox.size())]
        set_tracked_folders(folders)
        self.parent.log("Folder list updated.")
        save_config()

    def build_system_tab(self):
        frame = ttk.Frame(self.tab_system)
        frame.pack(fill=tk.BOTH, expand=True, pady=10, padx=10)
        ttk.Button(frame, text="Clean System Cache", command=lambda: self.run_task(clean_system_cache)).pack(pady=5)
        ttk.Button(frame, text="Clean External Drives", command=lambda: self.run_task(clean_external_drives)).pack(pady=5)
        self.sys_log = tk.Text(frame, height=8, wrap="word")
        self.sys_log.pack(fill=tk.BOTH, expand=True, pady=5)

    def run_task(self, task_func):
        def worker():
            result, _ = task_func(lambda m, s: self.sys_log.insert(tk.END, m + "\n"))
            self.sys_log.insert(tk.END, result + "\n")
            self.sys_log.see(tk.END)
        threading.Thread(target=worker, daemon=True).start()

    def build_monitor_tab(self):
        monitor = ActivityMonitor(self.tab_monitor)
        monitor.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

# -----------------------------------------
#  Main Entry
# -----------------------------------------
def main():
    setup_logging()
    load_config()
    app = RemoApp()
    app.mainloop()

if __name__ == "__main__":
    main()
