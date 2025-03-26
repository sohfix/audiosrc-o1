#!/usr/bin/env python3
import configparser
import hashlib
import logging
import os
import platform
import re
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import feedparser
import httpx
import requests

# --- Constants & Defaults ---
DEFAULT_TIMEOUT = 10
DEFAULT_MAX_RETRIES = 3
DEFAULT_INITIAL_BACKOFF = 2
DEFAULT_HTTPS_ONLY = False
DEFAULT_GENERATE_HASH = False
VERSION = (
    "2.0.0 [Enhanced Update, Verbose Logging, Extended Server Info & File Verification]"
)


# --- Configuration Functions ---
def get_config_path():
    if platform.system().lower().startswith("windows"):
        return r"C:\vrip_tools\vrip.ini"
    else:
        home_dir = os.path.expanduser("~")
        return os.path.join(home_dir, "programs", "vrip-ini", "vrip.ini")


def init_config():
    config_path = get_config_path()
    config_dir = os.path.dirname(config_path)
    if not os.path.exists(config_dir):
        os.makedirs(config_dir, exist_ok=True)
    config = configparser.ConfigParser()
    if os.path.exists(config_path):
        config.read(config_path)
    else:
        config["user"] = {"name": "", "password": ""}
        config["system"] = {
            "os": platform.system().lower(),
            "default_output_dir": (
                r"C:\vrip_tools\downloads"
                if platform.system().lower().startswith("windows")
                else os.path.join(os.path.expanduser("~"), "podcasts")
            ),
            "download_timeout": str(DEFAULT_TIMEOUT),
            "max_retries": str(DEFAULT_MAX_RETRIES),
            "initial_retry_backoff": str(DEFAULT_INITIAL_BACKOFF),
            "https_only": str(DEFAULT_HTTPS_ONLY),
            "generate_hash": str(DEFAULT_GENERATE_HASH),
        }
        config["logging"] = {
            "log_dir": (
                r"C:\vrip_tools\logs"
                if platform.system().lower().startswith("windows")
                else os.path.join(os.path.expanduser("~"), "pylogs", "vrip")
            ),
            "log_level": "INFO",
        }
        config["Podcasts"] = {"podcast_list": ""}
        with open(config_path, "w") as f:
            config.write(f)
    return config, config_path


def save_config(config, config_path):
    with open(config_path, "w") as f:
        config.write(f)


# --- Utility Functions ---
def compute_sha256(file_path):
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


def verify_file_integrity(file_path):
    hash_file = file_path + ".sha256"
    if not os.path.exists(hash_file):
        return False
    with open(hash_file, "r") as hf:
        expected = hf.read().strip()
    return compute_sha256(file_path) == expected


def build_episode_filename(original_title, fmt):
    def sanitize(text):
        return "".join(c for c in text if c.isalnum() or c in " _-").rstrip()

    if fmt == "daily":
        m = re.match(r"^(.*)\s+(\d{6})$", original_title)
        if m:
            main_part, date_part = m.groups()
            return f"{date_part} {sanitize(main_part)}".strip()
    return sanitize(original_title)


def ensure_output_dir(output_dir):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)


def parse_podcast_list(config):
    line = config["Podcasts"].get("podcast_list", "").strip()
    podcasts = []
    if line:
        entries = [e.strip() for e in line.split(";") if e.strip()]
        for entry in entries:
            parts = [p.strip() for p in entry.split(" : ")]
            if len(parts) == 3:
                podcasts.append((parts[0], parts[1], parts[2]))
    return podcasts


def human_readable_speed(bps):
    if bps < 1024:
        return f"{bps:.2f} B/s"
    elif bps < 1024 * 1024:
        return f"{bps / 1024:.2f} KB/s"
    else:
        return f"{bps / (1024 * 1024):.2f} MB/s"


def get_extended_server_info(url, timeout=DEFAULT_TIMEOUT):
    try:
        with httpx.Client(http2=True, timeout=timeout) as client:
            response = client.head(url)
            info = {
                "Server": response.headers.get("server", "Unknown"),
                "HTTP Version": response.http_version,
                "Content-Type": response.headers.get("content-type", "Unknown"),
                "Content-Length": response.headers.get("content-length", "Unknown"),
                "Date": response.headers.get("date", "Unknown"),
            }
            return info
    except Exception as e:
        return {"Error": str(e)}


# --- Download Functions ---
def download_with_progress(
    url,
    output_path,
    progress_callback=None,
    timeout=DEFAULT_TIMEOUT,
    max_retries=DEFAULT_MAX_RETRIES,
    initial_backoff=DEFAULT_INITIAL_BACKOFF,
):
    start_time = time.time()
    for attempt in range(1, max_retries + 1):
        try:
            config, _ = init_config()
            if config["system"].getboolean(
                "https_only", fallback=DEFAULT_HTTPS_ONLY
            ) and not url.lower().startswith("https"):
                raise requests.RequestException("Non-HTTPS URL rejected.")
            response = requests.get(url, stream=True, timeout=timeout)
            response.raise_for_status()
            total = int(response.headers.get("content-length", 0))
            downloaded = 0
            with open(output_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=4096):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        elapsed = time.time() - start_time
                        speed = downloaded / elapsed if elapsed > 0 else 0
                        if progress_callback:
                            progress_callback(downloaded, total, speed, elapsed)
            # Generate and verify hash if enabled
            if config["system"].getboolean(
                "generate_hash", fallback=DEFAULT_GENERATE_HASH
            ):
                digest = compute_sha256(output_path)
                with open(output_path + ".sha256", "w") as hf:
                    hf.write(digest)
                if not verify_file_integrity(output_path):
                    raise Exception("Hash verification failed")
            return True
        except Exception as e:
            logging.exception(f"Attempt {attempt} failed for {url}")
            time.sleep(initial_backoff * (2 ** (attempt - 1)))
    return False


def download_podcast_rss(
    rss_url,
    output_dir,
    count=None,
    searchby=None,
    verbose=False,
    oldest_first=False,
    format_str="default",
    progress_callback=None,
    episode_callback=None,
):
    ensure_output_dir(output_dir)
    feed = feedparser.parse(rss_url)
    if not feed.entries:
        raise Exception("No entries found in RSS feed.")
    entries = feed.entries
    if searchby:
        entries = [e for e in entries if searchby.lower() in e.title.lower()]
    if not entries:
        raise Exception("No entries match the search term.")

    def get_date(e):
        if hasattr(e, "published_parsed") and e.published_parsed:
            return time.mktime(e.published_parsed)
        elif hasattr(e, "updated_parsed") and e.updated_parsed:
            return time.mktime(e.updated_parsed)
        return 0

    entries.sort(key=get_date, reverse=not oldest_first)
    if count:
        entries = entries[:count]
    for e in entries:
        title = e.title
        if e.enclosures:
            link = e.enclosures[0].href
        else:
            continue
        if episode_callback:
            episode_callback(title, link)
        filename = build_episode_filename(title, format_str) + ".mp3"
        file_path = os.path.join(output_dir, filename)
        # --- File Existence & Integrity Check ---
        if os.path.exists(file_path):
            incomplete = False
            if e.enclosures and e.enclosures[0].get("length"):
                try:
                    expected = int(e.enclosures[0].get("length"))
                    if os.path.getsize(file_path) < expected:
                        incomplete = True
                except Exception:
                    incomplete = True
            else:
                if os.path.getsize(file_path) == 0:
                    incomplete = True
            config, _ = init_config()
            if not incomplete and config["system"].getboolean(
                "generate_hash", fallback=DEFAULT_GENERATE_HASH
            ):
                # If hash file missing or verification fails, mark as incomplete
                if os.path.exists(file_path + ".sha256"):
                    if not verify_file_integrity(file_path):
                        incomplete = True
                else:
                    incomplete = True
            if not incomplete:
                # Skip this episode – file exists and appears complete.
                continue
        if verbose:
            print(f"Downloading: {title}")
        success = download_with_progress(link, file_path, progress_callback)
        if not success:
            raise Exception(f"Failed to download: {title}")


# --- Main GUI Application ---
class VRipGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("vrip Podcast Downloader")
        self.style = ttk.Style(self)
        self.style.theme_use("clam")
        self.geometry("650x500")
        self.create_widgets()

    def create_widgets(self):
        main_frame = ttk.Frame(self, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            main_frame, text="vrip Podcast Downloader", font=("Helvetica", 16, "bold")
        ).pack(pady=10)
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(pady=20)
        ttk.Button(
            btn_frame,
            text="Download Podcasts",
            command=self.open_download_window,
            width=25,
        ).grid(row=0, column=0, pady=5)
        ttk.Button(
            btn_frame, text="Update Podcasts", command=self.open_update_window, width=25
        ).grid(row=1, column=0, pady=5)
        ttk.Button(
            btn_frame, text="Settings", command=self.open_settings_window, width=25
        ).grid(row=2, column=0, pady=5)
        ttk.Button(
            btn_frame, text="Manual & About", command=self.open_manual_window, width=25
        ).grid(row=3, column=0, pady=5)
        ttk.Button(btn_frame, text="Exit", command=self.quit, width=25).grid(
            row=4, column=0, pady=5
        )

    # ----------------- Download Window with Dashboard -----------------
    def open_download_window(self):
        win = tk.Toplevel(self)
        win.title("Download Podcasts")
        win.geometry("650x600")
        frame = ttk.Frame(win, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)

        # Mode selection
        mode = tk.StringVar(value="stored")
        ttk.Label(frame, text="Select Download Mode:", font=("Helvetica", 12)).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Radiobutton(
            frame, text="Stored Podcast", variable=mode, value="stored"
        ).grid(row=1, column=0, sticky="w", padx=5)
        ttk.Radiobutton(
            frame, text="Custom RSS URL", variable=mode, value="custom"
        ).grid(row=1, column=1, sticky="w", padx=5)

        # Stored podcast dropdown
        config, _ = init_config()
        podcasts = parse_podcast_list(config)
        ttk.Label(frame, text="Stored Podcasts:").grid(
            row=2, column=0, sticky="w", pady=(10, 0)
        )
        stored_cb = ttk.Combobox(
            frame, values=[p[1] for p in podcasts], state="readonly", width=40
        )
        stored_cb.grid(row=2, column=1, sticky="w", pady=(10, 0))
        if podcasts:
            stored_cb.current(0)

        # Custom RSS inputs
        ttk.Label(frame, text="RSS URL:").grid(
            row=3, column=0, sticky="w", pady=(10, 0)
        )
        rss_entry = ttk.Entry(frame, width=50)
        rss_entry.grid(row=3, column=1, sticky="w", pady=(10, 0))
        ttk.Label(frame, text="Output Directory:").grid(
            row=4, column=0, sticky="w", pady=(10, 0)
        )
        output_entry = ttk.Entry(frame, width=50)
        output_entry.grid(row=4, column=1, sticky="w", pady=(10, 0))
        output_entry.insert(0, config["system"].get("default_output_dir", ""))

        # Options
        oldest = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text="Download Oldest First", variable=oldest).grid(
            row=5, column=0, sticky="w", pady=(10, 0)
        )
        ttk.Label(frame, text="Max Episodes (blank for all):").grid(
            row=6, column=0, sticky="w", pady=(10, 0)
        )
        count_entry = ttk.Entry(frame, width=10)
        count_entry.grid(row=6, column=1, sticky="w", pady=(10, 0))
        ttk.Label(frame, text="Search Term (optional):").grid(
            row=7, column=0, sticky="w", pady=(10, 0)
        )
        search_entry = ttk.Entry(frame, width=30)
        search_entry.grid(row=7, column=1, sticky="w", pady=(10, 0))
        ttk.Label(frame, text="Filename Format (default/daily):").grid(
            row=8, column=0, sticky="w", pady=(10, 0)
        )
        format_entry = ttk.Entry(frame, width=10)
        format_entry.grid(row=8, column=1, sticky="w", pady=(10, 0))
        format_entry.insert(0, "default")

        # Dashboard: Progress, Speed, Elapsed, Server Info
        progress_var = tk.DoubleVar(value=0)
        progress_bar = ttk.Progressbar(
            frame, variable=progress_var, maximum=100, length=400
        )
        progress_bar.grid(row=9, column=0, columnspan=2, sticky="we", pady=(20, 5))
        status_label = ttk.Label(frame, text="Status: Idle")
        status_label.grid(row=10, column=0, columnspan=2, sticky="w", pady=(0, 5))
        speed_label = ttk.Label(frame, text="Speed: 0 B/s")
        speed_label.grid(row=11, column=0, sticky="w")
        elapsed_label = ttk.Label(frame, text="Elapsed: 0 sec")
        elapsed_label.grid(row=11, column=1, sticky="w")
        server_info_label = ttk.Label(
            frame, text="Server Info: N/A", anchor="w", justify="left"
        )
        server_info_label.grid(row=12, column=0, columnspan=2, sticky="w", pady=(10, 0))

        # Callback to update progress dashboard
        def update_progress(downloaded, total, speed, elapsed):
            def update():
                percent = (downloaded / total * 100) if total > 0 else 0
                progress_var.set(percent)
                status_label.config(text=f"Downloading... {int(percent)}%")
                speed_label.config(text=f"Speed: {human_readable_speed(speed)}")
                elapsed_label.config(text=f"Elapsed: {elapsed:.2f} sec")

            win.after(0, update)

        # Callback to update server info before each file
        def update_server_info(title, url):
            info = get_extended_server_info(url)

            def update():
                info_text = f"Title: {title}\n" + "\n".join(
                    f"{k}: {v}" for k, v in info.items()
                )
                server_info_label.config(text=info_text)

            win.after(0, update)

        def start_download():
            if mode.get() == "stored":
                if not podcasts:
                    messagebox.showerror("Error", "No stored podcasts available.")
                    return
                index = stored_cb.current()
                rss_url, _, out_dir = podcasts[index]
            else:
                rss_url = rss_entry.get().strip()
                out_dir = output_entry.get().strip()
                if not rss_url:
                    messagebox.showerror("Error", "Please enter an RSS URL.")
                    return
            count = (
                int(count_entry.get().strip())
                if count_entry.get().strip().isdigit()
                else None
            )
            search_term = search_entry.get().strip()
            fmt = format_entry.get().strip() or "default"

            def run_download():
                try:
                    download_podcast_rss(
                        rss_url,
                        out_dir,
                        count,
                        search_term,
                        verbose=True,
                        oldest_first=oldest.get(),
                        format_str=fmt,
                        progress_callback=update_progress,
                        episode_callback=update_server_info,
                    )
                    win.after(
                        0,
                        lambda: messagebox.showinfo(
                            "Download", "Download completed successfully."
                        ),
                    )
                    win.after(0, lambda: progress_var.set(0))
                    win.after(0, lambda: status_label.config(text="Status: Completed"))
                except Exception as ex:
                    win.after(
                        0, lambda: messagebox.showerror("Download Error", str(ex))
                    )
                    win.after(0, lambda: progress_var.set(0))
                    win.after(0, lambda: status_label.config(text="Status: Error"))

            threading.Thread(target=run_download, daemon=True).start()

        ttk.Button(frame, text="Start Download", command=start_download).grid(
            row=13, column=0, columnspan=2, pady=20
        )

    # ----------------- Update Window with Dashboard -----------------
    def open_update_window(self):
        win = tk.Toplevel(self)
        win.title("Update Podcasts")
        win.geometry("650x600")
        frame = ttk.Frame(win, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)

        mode = tk.StringVar(value="all")
        ttk.Label(frame, text="Select Update Mode:", font=("Helvetica", 12)).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Radiobutton(
            frame, text="Update All Podcasts", variable=mode, value="all"
        ).grid(row=1, column=0, sticky="w", pady=(5, 0))
        ttk.Radiobutton(
            frame, text="Update One Podcast", variable=mode, value="one"
        ).grid(row=2, column=0, sticky="w", pady=(5, 0))
        config, _ = init_config()
        podcasts = parse_podcast_list(config)
        ttk.Label(frame, text="Select Podcast (if applicable):").grid(
            row=3, column=0, sticky="w", pady=(10, 0)
        )
        podcast_cb = ttk.Combobox(
            frame, values=[p[1] for p in podcasts], state="readonly", width=40
        )
        podcast_cb.grid(row=3, column=1, sticky="w")
        if podcasts:
            podcast_cb.current(0)

        # Dashboard elements (similar to download window)
        progress_var = tk.DoubleVar(value=0)
        progress_bar = ttk.Progressbar(
            frame, variable=progress_var, maximum=100, length=400
        )
        progress_bar.grid(row=4, column=0, columnspan=2, sticky="we", pady=(20, 5))
        status_label = ttk.Label(frame, text="Status: Idle")
        status_label.grid(row=5, column=0, columnspan=2, sticky="w", pady=(0, 5))
        speed_label = ttk.Label(frame, text="Speed: 0 B/s")
        speed_label.grid(row=6, column=0, sticky="w")
        elapsed_label = ttk.Label(frame, text="Elapsed: 0 sec")
        elapsed_label.grid(row=6, column=1, sticky="w")
        server_info_label = ttk.Label(
            frame, text="Server Info: N/A", anchor="w", justify="left"
        )
        server_info_label.grid(row=7, column=0, columnspan=2, sticky="w", pady=(10, 0))

        def update_progress(downloaded, total, speed, elapsed):
            def update():
                percent = (downloaded / total * 100) if total > 0 else 0
                progress_var.set(percent)
                status_label.config(text=f"Downloading... {int(percent)}%")
                speed_label.config(text=f"Speed: {human_readable_speed(speed)}")
                elapsed_label.config(text=f"Elapsed: {elapsed:.2f} sec")

            win.after(0, update)

        def update_server_info(title, url):
            info = get_extended_server_info(url)

            def update():
                info_text = f"Title: {title}\n" + "\n".join(
                    f"{k}: {v}" for k, v in info.items()
                )
                server_info_label.config(text=info_text)

            win.after(0, update)

        def start_update():
            def run_update():
                try:
                    if mode.get() == "all":
                        for rss_url, _, out_dir in podcasts:
                            download_podcast_rss(
                                rss_url,
                                out_dir,
                                verbose=True,
                                progress_callback=update_progress,
                                episode_callback=update_server_info,
                            )
                        win.after(
                            0,
                            lambda: messagebox.showinfo(
                                "Update", "All podcasts updated successfully."
                            ),
                        )
                    else:
                        if not podcasts:
                            win.after(
                                0,
                                lambda: messagebox.showerror(
                                    "Error", "No stored podcasts available."
                                ),
                            )
                            return
                        index = podcast_cb.current()
                        rss_url, name, out_dir = podcasts[index]
                        download_podcast_rss(
                            rss_url,
                            out_dir,
                            verbose=True,
                            progress_callback=update_progress,
                            episode_callback=update_server_info,
                        )
                        win.after(
                            0,
                            lambda: messagebox.showinfo(
                                "Update", f"Podcast '{name}' updated successfully."
                            ),
                        )
                    win.after(0, lambda: progress_var.set(0))
                    win.after(0, lambda: status_label.config(text="Status: Completed"))
                except Exception as ex:
                    win.after(0, lambda: messagebox.showerror("Update Error", str(ex)))
                    win.after(0, lambda: progress_var.set(0))
                    win.after(0, lambda: status_label.config(text="Status: Error"))

            threading.Thread(target=run_update, daemon=True).start()

        ttk.Button(frame, text="Start Update", command=start_update).grid(
            row=8, column=0, columnspan=2, pady=20
        )

    # ----------------- Settings Window -----------------
    def open_settings_window(self):
        win = tk.Toplevel(self)
        win.title("Settings")
        win.geometry("600x500")
        frame = ttk.Frame(win, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)
        config, config_path = init_config()
        # User settings
        ttk.Label(frame, text="User Settings", font=("Helvetica", 12, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(frame, text="Name:").grid(row=1, column=0, sticky="w", pady=(5, 0))
        name_entry = ttk.Entry(frame, width=30)
        name_entry.grid(row=1, column=1, sticky="w", pady=(5, 0))
        name_entry.insert(0, config["user"].get("name", ""))
        ttk.Label(frame, text="Password:").grid(
            row=2, column=0, sticky="w", pady=(5, 0)
        )
        password_entry = ttk.Entry(frame, width=30, show="*")
        password_entry.grid(row=2, column=1, sticky="w", pady=(5, 0))
        password_entry.insert(0, config["user"].get("password", ""))
        # System settings
        ttk.Label(frame, text="System Settings", font=("Helvetica", 12, "bold")).grid(
            row=3, column=0, sticky="w", pady=(15, 0)
        )
        ttk.Label(frame, text="Default Output Directory:").grid(
            row=4, column=0, sticky="w", pady=(5, 0)
        )
        output_entry = ttk.Entry(frame, width=40)
        output_entry.grid(row=4, column=1, sticky="w", pady=(5, 0))
        output_entry.insert(0, config["system"].get("default_output_dir", ""))
        ttk.Label(frame, text="Download Timeout (sec):").grid(
            row=5, column=0, sticky="w", pady=(5, 0)
        )
        timeout_entry = ttk.Entry(frame, width=10)
        timeout_entry.grid(row=5, column=1, sticky="w", pady=(5, 0))
        timeout_entry.insert(
            0, config["system"].get("download_timeout", str(DEFAULT_TIMEOUT))
        )
        ttk.Label(frame, text="HTTPS Only (True/False):").grid(
            row=6, column=0, sticky="w", pady=(5, 0)
        )
        https_entry = ttk.Entry(frame, width=10)
        https_entry.grid(row=6, column=1, sticky="w", pady=(5, 0))
        https_entry.insert(
            0, config["system"].get("https_only", str(DEFAULT_HTTPS_ONLY))
        )
        ttk.Label(frame, text="Generate Hash (True/False):").grid(
            row=7, column=0, sticky="w", pady=(5, 0)
        )
        hash_entry = ttk.Entry(frame, width=10)
        hash_entry.grid(row=7, column=1, sticky="w", pady=(5, 0))
        hash_entry.insert(
            0, config["system"].get("generate_hash", str(DEFAULT_GENERATE_HASH))
        )
        # Podcast list management
        ttk.Label(
            frame,
            text="Podcast List (Format: RSS_LINK : NAME_ID : OUTPUT_DIRECTORY)",
            font=("Helvetica", 12, "bold"),
        ).grid(row=8, column=0, columnspan=2, sticky="w", pady=(15, 0))
        podcast_text = tk.Text(frame, width=60, height=6)
        podcast_text.grid(row=9, column=0, columnspan=2, pady=(5, 0))
        podcast_text.insert(tk.END, config["Podcasts"].get("podcast_list", ""))

        def save_settings():
            config["user"]["name"] = name_entry.get().strip()
            config["user"]["password"] = password_entry.get().strip()
            config["system"]["default_output_dir"] = output_entry.get().strip()
            config["system"]["download_timeout"] = timeout_entry.get().strip()
            config["system"]["https_only"] = https_entry.get().strip()
            config["system"]["generate_hash"] = hash_entry.get().strip()
            config["Podcasts"]["podcast_list"] = podcast_text.get("1.0", tk.END).strip()
            save_config(config, config_path)
            messagebox.showinfo("Settings", "Settings saved successfully.")

        ttk.Button(frame, text="Save Settings", command=save_settings).grid(
            row=10, column=0, columnspan=2, pady=15
        )

    # ----------------- Manual & About Window -----------------
    def open_manual_window(self):
        win = tk.Toplevel(self)
        win.title("Manual & About")
        win.geometry("600x500")
        frame = ttk.Frame(win, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)
        text = tk.Text(frame, wrap="word")
        text.pack(fill=tk.BOTH, expand=True)
        manual = f"""
vrip {VERSION}

Overview:
vrip is a podcast downloader that uses RSS feeds to download episodes.
It supports a full GUI dashboard showing download progress, speed, elapsed time,
and extended server information – all without using the console.

Features:
- Download episodes from stored podcasts or a custom RSS URL.
- Update podcasts (all or one) with full dashboard feedback.
- Configurable settings: default output directory, timeout, HTTPS‑only, hash generation.
- Detailed dashboard: loading bar, data speed/rate, server info, and elapsed time.
- Skips files that already exist and are complete.
- Manual & About screen with version info.

Usage:
1. Download: Choose a stored podcast or enter a custom RSS URL.
2. Update: Update all podcasts or select one to update.
3. Settings: Edit user credentials, system settings, and manage the podcast list.
4. Manual & About: Read this manual and version information.

Enjoy using vrip!
        """
        text.insert(tk.END, manual)
        text.config(state="disabled")


if __name__ == "__main__":
    app = VRipGUI()
    app.mainloop()
