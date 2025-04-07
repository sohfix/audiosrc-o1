# OPTIMIZED FOR WINDOWS

import json
import logging
import os
import queue
import shutil
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk

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


def ensure_config_dir():
    """Ensure that the configuration directory exists."""
    if not os.path.exists(CONFIG_DIR):
        try:
            os.makedirs(CONFIG_DIR)
        except Exception as e:
            messagebox.showerror(
                "Configuration Error", f"Could not create configuration directory:\n{e}"
            )
            sys.exit(1)


def load_config():
    """
    Load backup configuration from a JSON file in CONFIG_DIR.
    If it doesn't exist, create one with default values.
    """
    ensure_config_dir()
    default_config = {
        "source_folders": [os.path.expanduser("~/Documents")],
        "backup_destination": "D:/Backup",
    }
    if not os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(default_config, f, indent=4)
            messagebox.showinfo(
                "Configuration Created",
                f"Default config created at {CONFIG_FILE}.\nPlease review and update it as needed.",
            )
            return default_config
        except Exception as e:
            messagebox.showerror(
                "Configuration Error", f"Error creating default config:\n{e}"
            )
            sys.exit(1)
    else:
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            messagebox.showerror(
                "Configuration Error", f"Error reading config file:\n{e}"
            )
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
            messagebox.showerror(
                "Configuration Error",
                f"Source folder does not exist:\n{folder}\nPlease update {CONFIG_FILE}.",
            )
            valid = False

    # Check backup destination folder
    backup_dest = config.get("backup_destination", "")
    if not backup_dest:
        messagebox.showerror(
            "Configuration Error", f"No backup destination specified in {CONFIG_FILE}."
        )
        valid = False
    elif not os.path.isdir(backup_dest):
        try:
            os.makedirs(backup_dest)
        except Exception as e:
            messagebox.showerror(
                "Configuration Error",
                f"Backup destination folder could not be created:\n{backup_dest}\nError: {e}",
            )
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
    """Copy a file if the source is newer; update progress afterward."""
    global files_copied, files_skipped, errors_count, files_processed
    dest_dir = os.path.dirname(dest_file)
    if not os.path.exists(dest_dir):
        try:
            os.makedirs(dest_dir)
        except Exception as e:
            logging.error(f"Error creating directory {dest_dir}: {e}")
            errors_count += 1
            return

    try:
        if os.path.exists(dest_file):
            src_mtime = os.path.getmtime(src_file)
            dest_mtime = os.path.getmtime(dest_file)
            # If the destination is up-to-date, skip copying
            if src_mtime <= dest_mtime:
                logging.info(f"Skipped (up-to-date): {src_file}")
                files_skipped += 1
                return
        shutil.copy2(src_file, dest_file)
        logging.info(f"Copied: {src_file} to {dest_file}")
        files_copied += 1
    except Exception as e:
        logging.error(f"Error copying {src_file} to {dest_file}: {e}")
        errors_count += 1
    finally:
        files_processed += 1
        # Calculate and send progress update
        progress_percent = (
            int((files_processed / total_files) * 100) if total_files > 0 else 100
        )
        progress_queue.put(
            (
                "update",
                progress_percent,
                f"Processed {files_processed} of {total_files} files.",
            )
        )


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
    global total_files
    config = load_config()
    validate_config(config)
    source_folders = config.get("source_folders", [])
    backup_destination = config.get("backup_destination", "")

    # Count total files across all source folders
    total_files = 0
    for folder in source_folders:
        if os.path.exists(folder):
            total_files += count_files_in_folder(folder)
        else:
            logging.warning(f"Source folder does not exist: {folder}")

    if total_files == 0:
        progress_queue.put(("done", 0, "No files to backup."))
        return

    # Process each source folder
    for folder in source_folders:
        if os.path.exists(folder):
            progress_queue.put(("update", None, f"Backing up folder: {folder}"))
            backup_folder(folder, backup_destination)
        else:
            logging.warning(f"Source folder does not exist: {folder}")
            global errors_count
            errors_count += 1

    # Send final summary
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


def update_progress(root, progress_bar, status_label):
    """
    Poll the progress queue and update the GUI.
    When the backup is complete, display a summary popup.
    """
    try:
        while True:
            msg = progress_queue.get_nowait()
            if msg[0] == "update":
                percent = msg[1]
                text = msg[2]
                if percent is not None:
                    progress_bar["value"] = percent
                status_label.config(text=text)
            elif msg[0] == "done":
                percent = msg[1]
                summary = msg[2]
                progress_bar["value"] = percent
                status_label.config(text="Backup Completed")
                show_summary_popup(root, summary)
                return
    except queue.Empty:
        pass
    root.after(100, update_progress, root, progress_bar, status_label)


def show_summary_popup(root, summary):
    """
    Display a popup window showing the final backup summary.
    The user must click OK to exit.
    """
    summary_win = tk.Toplevel(root)
    summary_win.title("Backup Summary")
    summary_win.geometry("400x200")
    summary_label = tk.Label(
        summary_win, text=summary, justify="left", padx=10, pady=10
    )
    summary_label.pack(expand=True, fill="both")
    ok_button = tk.Button(summary_win, text="OK", command=root.destroy)
    ok_button.pack(pady=10)
    summary_win.transient(root)
    summary_win.grab_set()
    root.wait_window(summary_win)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()],
    )

    # Set up main Tkinter window
    root = tk.Tk()
    root.title("Backup Progress")
    root.geometry("500x150")

    # Progress bar widget
    progress_bar = ttk.Progressbar(
        root, orient="horizontal", length=400, mode="determinate"
    )
    progress_bar.pack(pady=20)

    # Status label for current operation
    status_label = tk.Label(root, text="Starting backup...", padx=10)
    status_label.pack()

    # Start the backup process in a background thread
    start_backup_thread()

    # Begin polling the progress queue to update the UI
    root.after(100, update_progress, root, progress_bar, status_label)
    root.mainloop()


if __name__ == "__main__":
    main()
