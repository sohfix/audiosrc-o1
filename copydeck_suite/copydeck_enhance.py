import os
import sys
import json
import shutil
import logging
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import queue
import platform

# Global counters for backup statistics
files_copied = 0
files_skipped = 0
errors_count = 0
files_processed = 0
total_files = 0

# Queue for inter-thread progress updates
progress_queue = queue.Queue()

# Configuration directory and file location
CONFIG_DIR = r"C:/CopyDeckFiles"
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")


def print_banner():
    """Prints the cool ASCII banner at the top of the console."""
    banner = r"""
 ██████╗ ██████╗ ██████╗ ██╗   ██╗    ██████╗ ███████╗ ██████╗██╗  ██╗     
██╔════╝██╔═══██╗██╔══██╗╚██╗ ██╔╝    ██╔══██╗██╔════╝██╔════╝██║ ██╔╝     
██║     ██║   ██║██████╔╝ ╚████╔╝     ██║  ██║█████╗  ██║     █████╔╝      
██║     ██║   ██║██╔═══╝   ╚██╔╝      ██║  ██║██╔══╝  ██║     ██╔═██╗      
╚██████╗╚██████╔╝██║        ██║       ██████╔╝███████╗╚██████╗██║  ██╗     
 ╚═════╝ ╚═════╝ ╚═╝        ╚═╝       ╚═════╝ ╚══════╝ ╚═════╝╚═╝  ╚═╝     

██████╗ ██╗   ██╗    ███╗   ██╗██╗ ██████╗ ██████╗ ██╗      █████╗ ███████╗
██╔══██╗╚██╗ ██╔╝    ████╗  ██║██║██╔════╝██╔═══██╗██║     ██╔══██╗██╔════╝
██████╔╝ ╚████╔╝     ██╔██╗ ██║██║██║     ██║   ██║██║     ███████║███████╗
██╔══██╗  ╚██╔╝      ██║╚██╗██║██║██║     ██║   ██║██║     ██╔══██║╚════██║
██████╔╝   ██║       ██║ ╚████║██║╚██████╗╚██████╔╝███████╗██║  ██║███████║
╚═════╝    ╚═╝       ╚═╝  ╚═══╝╚═╝ ╚═════╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝╚══════╝

"""
    print(banner)


def ensure_config_dir():
    """Ensure that the configuration directory exists."""
    if not os.path.exists(CONFIG_DIR):
        try:
            os.makedirs(CONFIG_DIR)
        except Exception as e:
            messagebox.showerror("Configuration Error", f"Could not create configuration directory:\n{e}")
            sys.exit(1)


def load_config():
    """
    Load backup configuration from a JSON file in CONFIG_DIR.
    If it doesn't exist, create one with default values.
    """
    ensure_config_dir()
    default_config = {
        "source_folders": [os.path.expanduser("~/Documents")],
        "backup_destination": "D:/Backup"
    }
    if not os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(default_config, f, indent=4)
            messagebox.showinfo("Configuration Created",
                                f"Default config created at {CONFIG_FILE}.\nPlease review and update it as needed.")
            return default_config
        except Exception as e:
            messagebox.showerror("Configuration Error", f"Error creating default config:\n{e}")
            sys.exit(1)
    else:
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            messagebox.showerror("Configuration Error", f"Error reading config file:\n{e}")
            sys.exit(1)


def validate_config(config):
    """
    Verify that each source folder exists and the backup destination is valid.
    For missing input directories, display an error and exit.
    For the backup destination, attempt to create it if it doesn't exist.
    """
    valid = True
    # Check each source folder
    for folder in config.get("source_folders", []):
        if not os.path.isdir(folder):
            messagebox.showerror("Configuration Error",
                                 f"Source folder does not exist:\n{folder}\nPlease update {CONFIG_FILE}.")
            valid = False

    # Check backup destination folder
    backup_dest = config.get("backup_destination", "")
    if not backup_dest:
        messagebox.showerror("Configuration Error",
                             f"No backup destination specified in {CONFIG_FILE}.")
        valid = False
    elif not os.path.isdir(backup_dest):
        try:
            os.makedirs(backup_dest)
        except Exception as e:
            messagebox.showerror("Configuration Error",
                                 f"Backup destination folder could not be created:\n{backup_dest}\nError: {e}")
            valid = False

    if not valid:
        sys.exit(1)


def count_files_in_folder(source_folder):
    """Count total files in a folder recursively."""
    count = 0
    for _, _, files in os.walk(source_folder):
        count += len(files)
    return count


def backup_file(src_file, dest_file):
    """
    Copy a file if the source is newer.
    Also update the console with the currently processing file using ANSI colors.
    """
    global files_copied, files_skipped, errors_count, files_processed
    dest_dir = os.path.dirname(dest_file)
    if not os.path.exists(dest_dir):
        try:
            os.makedirs(dest_dir)
        except Exception as e:
            logging.error(f"Error creating directory {dest_dir}: {e}")
            errors_count += 1
            return

    # Update the console with the file being processed
    sys.stdout.write("\r\033[93mProcessing: " + src_file + "\033[0m" + " " * 20)
    sys.stdout.flush()

    try:
        if os.path.exists(dest_file):
            src_mtime = os.path.getmtime(src_file)
            dest_mtime = os.path.getmtime(dest_file)
            # If destination is up-to-date, skip copying
            if src_mtime <= dest_mtime:
                files_skipped += 1
                return
        shutil.copy2(src_file, dest_file)
        files_copied += 1
    except Exception as e:
        logging.error(f"Error copying {src_file} to {dest_file}: {e}")
        errors_count += 1
    finally:
        files_processed += 1
        progress_percent = int((files_processed / total_files) * 100) if total_files > 0 else 100
        progress_queue.put(("update", progress_percent, f"Processed {files_processed} of {total_files} files."))


def backup_folder(source_folder, backup_destination):
    """
    Recursively back up files from source_folder.
    The destination will contain a subfolder named after the source folder's basename.
    """
    base_folder_name = os.path.basename(os.path.normpath(source_folder))
    for root, _, files in os.walk(source_folder):
        for file in files:
            src_file = os.path.join(root, file)
            rel_path = os.path.relpath(src_file, source_folder)
            dest_folder = os.path.join(backup_destination, base_folder_name)
            dest_file = os.path.join(dest_folder, rel_path)
            backup_file(src_file, dest_file)


def backup_worker():
    """
    Worker function to run the backup process in a separate thread.
    Loads configuration, counts total files, processes backups, and sends a final summary.
    """
    global total_files, files_copied, files_skipped, errors_count, files_processed
    files_copied = files_skipped = errors_count = files_processed = 0
    config = load_config()
    validate_config(config)
    source_folders = config.get("source_folders", [])
    backup_destination = config.get("backup_destination", "")

    total_files = 0
    for folder in source_folders:
        if os.path.exists(folder):
            total_files += count_files_in_folder(folder)
        else:
            logging.warning(f"Source folder does not exist: {folder}")

    if total_files == 0:
        progress_queue.put(("done", 0, "No files to backup."))
        return

    for folder in source_folders:
        if os.path.exists(folder):
            progress_queue.put(("update", None, f"Backing up folder: {folder}"))
            backup_folder(folder, backup_destination)
        else:
            logging.warning(f"Source folder does not exist: {folder}")
            errors_count += 1

    summary = (
        f"Backup Completed:\n\n"
        f"Files Copied: {files_copied}\n"
        f"Files Skipped: {files_skipped}\n"
        f"Errors: {errors_count}"
    )
    progress_queue.put(("done", 100, summary))


def start_backup_thread():
    """Start the backup process in a background thread."""
    thread = threading.Thread(target=backup_worker, daemon=True)
    thread.start()


def show_summary_popup(parent, summary):
    """
    Display a popup window showing the final backup summary.
    The user must click OK to continue.
    """
    messagebox.showinfo("Backup Summary", summary, parent=parent)


def run_backup_process(root, main_menu):
    """
    Hide the main menu frame, display the progress window,
    run the backup process, then return to the main menu.
    """
    # Hide main menu frame
    main_menu.pack_forget()
    progress_win = tk.Toplevel(root)
    progress_win.title("Backup Progress")
    progress_win.geometry("500x150")

    progress_bar = ttk.Progressbar(progress_win, orient="horizontal", length=400, mode="determinate")
    progress_bar.pack(pady=20)

    status_label = tk.Label(progress_win, text="Starting backup...", padx=10)
    status_label.pack()

    def update_progress():
        try:
            while True:
                msg = progress_queue.get_nowait()
                if msg[0] == "update":
                    percent = msg[1]
                    text = msg[2]
                    if percent is not None:
                        progress_bar['value'] = percent
                    status_label.config(text=text)
                elif msg[0] == "done":
                    percent = msg[1]
                    summary = msg[2]
                    progress_bar['value'] = percent
                    status_label.config(text="Backup Completed")
                    show_summary_popup(progress_win, summary)
                    progress_win.destroy()
                    # Re-show main menu frame
                    main_menu.pack(expand=True, fill="both", padx=20, pady=20)
                    return
        except queue.Empty:
            pass
        progress_win.after(100, update_progress)

    start_backup_thread()
    update_progress()


def on_backup_now(root, main_menu):
    """Handler for the Backup Now button."""
    run_backup_process(root, main_menu)


def auto_backup_trigger(root, main_menu):
    """
    Function triggered by the auto-backup timer.
    Shows a confirmation popup; if approved, runs the backup process.
    """
    answer = messagebox.askokcancel("Auto Backup",
                                    "Scheduled backup is ready.\nDo you want to backup now?",
                                    parent=root)
    if answer:
        run_backup_process(root, main_menu)
    else:
        main_menu.pack(expand=True, fill="both", padx=20, pady=20)


def on_set_auto_backup(root, main_menu, interval_hours):
    """
    Handler for setting auto backup.
    Hides the main menu frame and schedules auto backup after the selected interval.
    """
    try:
        interval = int(interval_hours)
    except ValueError:
        messagebox.showerror("Input Error", "Please select a valid interval.")
        return
    interval_ms = interval * 60 * 60 * 1000
    main_menu.pack_forget()
    messagebox.showinfo("Auto Backup Scheduled", f"Auto backup scheduled in {interval} hour(s).", parent=root)
    root.after(interval_ms, auto_backup_trigger, root, main_menu)


def main():
    # Enable ANSI escape sequence support on Windows 10
    if platform.system() == "Windows":
        os.system("")

    print_banner()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()]
    )

    root = tk.Tk()
    root.title("Backup Application")
    root.geometry("400x250")

    main_menu = tk.Frame(root)
    main_menu.pack(expand=True, fill="both", padx=20, pady=20)

    title_label = tk.Label(main_menu, text="Backup Application", font=("Arial", 16))
    title_label.pack(pady=10)

    backup_now_btn = tk.Button(main_menu, text="Backup Now", width=20,
                               command=lambda: on_backup_now(root, main_menu))
    backup_now_btn.pack(pady=5)

    auto_frame = tk.Frame(main_menu)
    auto_frame.pack(pady=5)

    auto_label = tk.Label(auto_frame, text="Auto Backup Every:")
    auto_label.pack(side="left")

    interval_var = tk.StringVar(value="1")
    interval_options = ["1", "2", "3", "4"]
    interval_menu = tk.OptionMenu(auto_frame, interval_var, *interval_options)
    interval_menu.pack(side="left", padx=5)

    auto_backup_btn = tk.Button(auto_frame, text="Set Auto Backup",
                                command=lambda: on_set_auto_backup(root, main_menu, interval_var.get()))
    auto_backup_btn.pack(side="left", padx=5)

    exit_btn = tk.Button(main_menu, text="Exit", width=20, command=root.quit)
    exit_btn.pack(pady=10)

    root.mainloop()


if __name__ == "__main__":
    main()
