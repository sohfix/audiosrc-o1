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
    # Ensure all required sections/keys exist
    if "Settings" not in config:
        config["Settings"] = {}
    if "Directories" not in config:
        config["Directories"] = {}
    config["Settings"].setdefault("dark_mode", "true")
    config["Directories"].setdefault("paths", "")
    save_config()

def create_default_config():
    """Create a brand‐new config with default values."""
    config["Settings"] = {
        "dark_mode": "true",
    }
    config["Directories"] = {
        "paths": ""
    }
    save_config()

def save_config():
    """Write current config state to file."""
    with open(INI_PATH, "w") as f:
        config.write(f)
    logging.info("Config saved.")

# -----------------------------------------
#  Cleanup Logic
# -----------------------------------------
def remove_path(path):
    """Delete a file or folder (recursively). Logs result."""
    try:
        if os.path.isdir(path):
            shutil.rmtree(path)
            msg = f"Removed directory: {path}"
        elif os.path.exists(path):
            os.remove(path)
            msg = f"Removed file: {path}"
        else:
            msg = f"Path not found: {path}"
        logging.info(msg)
        return msg
    except Exception as e:
        msg = f"Error removing {path}: {e}"
        logging.error(msg)
        return msg

def move_exe_from_dist(base):
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
                summary.append(f"Moved {f} to {base}")
            except Exception as e:
                summary.append(f"Failed to move {f}: {e}")
    if not found_any:
        summary.append("No .exe files in 'dist'.")
    return summary

def remove_spec_files(directory):
    """Remove .spec files in `directory`."""
    return [
        remove_path(os.path.join(directory, f))
        for f in os.listdir(directory)
        if f.lower().endswith(".spec")
    ]

def remove_pycache_dirs(directory):
    """Remove __pycache__ dirs under `directory`, recursively."""
    summary = []
    for root, dirs, _ in os.walk(directory):
        for d in dirs:
            if d == "__pycache__":
                summary.append(remove_path(os.path.join(root, d)))
    return summary

def process_directory(path):
    """Perform the standard cleanup steps on one directory."""
    summary = [f"Processing: {path}"]
    if not os.path.isdir(path):
        return [f"Not a valid directory: {path}"]

    # 1) Move exe from dist (as in original code)
    summary += move_exe_from_dist(path)
    # 2) Remove build folder
    summary.append(remove_path(os.path.join(path, "build")))
    # 3) Remove dist folder
    summary.append(remove_path(os.path.join(path, "dist")))
    # 4) Remove .spec files
    summary += remove_spec_files(path)
    # 5) Remove __pycache__ directories
    summary += remove_pycache_dirs(path)
    summary.append("-" * 40)
    return summary

def main_cleanup():
    """Cleanup all directories from config, returning a text summary."""
    dir_list = get_tracked_folders()
    if not dir_list:
        return "No directories to process."
    results = []
    for d in dir_list:
        results += process_directory(d)
    return "\n".join(results)

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
    """Add path to `[Directories].paths` if not present."""
    dirs = get_tracked_folders()
    if path not in dirs:
        dirs.append(path)
        set_tracked_folders(dirs)
        logging.info(f"Added to config: {path}")
        return f"Added: {path}"
    return "Already exists."

def remove_directory_from_ini(path):
    """Remove path from `[Directories].paths`."""
    dirs = get_tracked_folders()
    if path in dirs:
        dirs.remove(path)
        set_tracked_folders(dirs)
        logging.info(f"Removed from config: {path}")
        return f"Removed: {path}"
    return "Not found in list."

# -----------------------------------------
#  GUI: Progress Window
# -----------------------------------------
class ProgressWindow(tk.Toplevel):
    """Simple window with an indeterminate Progressbar and optional banner."""
    def __init__(self, parent, title="Please wait..."):
        super().__init__(parent)
        self.title(title)
        self.geometry("300x100")
        self.resizable(False, False)
        # show banner if available
        if os.path.exists(BANNER_PATH):
            try:
                self.banner = tk.PhotoImage(file=BANNER_PATH)
                tk.Label(self, image=self.banner).pack()
            except Exception:
                pass
        ttk.Label(self, text=title).pack(pady=10)
        self.progress_bar = ttk.Progressbar(self, mode="indeterminate")
        self.progress_bar.pack(fill=tk.X, padx=20)
        self.progress_bar.start()

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
        self.log("REMO Cleaner")

    def load_icon(self):
        if os.path.exists(ICON_PATH):
            try:
                self.iconbitmap(ICON_PATH)
            except Exception as e:
                logging.error(f"Error loading icon: {e}")

    # -------------- Menubar --------------
    def create_menubar(self):
        menubar = tk.Menu(self)
        # File
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Exit", command=self.safe_exit)
        menubar.add_cascade(label="File", menu=file_menu)
        # Settings
        settings_menu = tk.Menu(menubar, tearoff=0)
        settings_menu.add_command(label="Open Settings...", command=self.open_settings_window)
        # Toggle dark mode item from menubar
        settings_menu.add_command(label="Toggle Dark Mode", command=self.toggle_dark_mode)
        menubar.add_cascade(label="Settings", menu=settings_menu)
        # Help
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="About", command=self.show_about)
        help_menu.add_command(label="Check for Updates", command=self.check_updates)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.config(menu=menubar)

    # -------------- Main UI --------------
    def create_main_widgets(self):
        # Banner
        if os.path.exists(BANNER_PATH):
            try:
                self.banner_image = tk.PhotoImage(file=BANNER_PATH)
                tk.Label(self, image=self.banner_image, bg=self["bg"]).pack(pady=5)
            except Exception as e:
                logging.error(f"Error loading banner: {e}")

        # Big Buttons
        frame = ttk.Frame(self)
        frame.pack(pady=10)
        ttk.Button(frame, text="Start Cleanup", command=self.start_cleanup).grid(row=0, column=0, padx=10)
        ttk.Button(frame, text="Exit", command=self.safe_exit).grid(row=0, column=1, padx=10)

        # Log window
        self.log_box = tk.Text(self, height=12, wrap="word")
        self.log_box.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.log_box.insert(tk.END, "REMO ready.\n")

    def start_cleanup(self):
        """Run main_cleanup() in a background thread."""
        self.log("🧹 Starting cleanup...")
        prog = ProgressWindow(self, title="Cleaning up projects...")
        def worker():
            result = main_cleanup()
            prog.destroy()
            self.log(result)
        threading.Thread(target=worker, daemon=True).start()

    def apply_dark_mode_style(self):
        """Set background/foreground for dark vs. light mode."""
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

    # -------------- Logging Helper --------------
    def log(self, msg):
        self.log_box.insert(tk.END, msg + "\n")
        self.log_box.see(tk.END)
        logging.info(msg)

    # -------------- Menubar Actions --------------
    def show_about(self):
        messagebox.showinfo("About", "REMO Cleaner fuck off")

    def check_updates(self):
        messagebox.showinfo("Check Updates", "No updates available at this time.")

    def safe_exit(self):
        self.destroy()
        self.quit()

    # -------------- Settings Window --------------
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

        # 1) General Tab
        self.tab_general = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_general, text="General")
        self.build_general_tab()

        # 2) Folders Tab
        self.tab_folders = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_folders, text="Folders")
        self.build_folders_tab()

    def build_general_tab(self):
        frame = ttk.Frame(self.tab_general)
        frame.pack(fill=tk.BOTH, expand=True, pady=10, padx=10)

        # Dark mode label/checkbox
        self.dark_var = tk.BooleanVar(value=self.dark_mode)
        dark_check = ttk.Checkbutton(frame, text="Use Dark Mode", variable=self.dark_var)
        dark_check.pack(anchor="w", pady=5)

        # Save button
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

        # Show current folder list
        self.folder_listbox = tk.Listbox(frame, selectmode=tk.SINGLE, height=8)
        self.folder_listbox.pack(fill=tk.BOTH, expand=True, side="left")

        # Populate
        for d in get_tracked_folders():
            self.folder_listbox.insert(tk.END, d)

        # Buttons
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
