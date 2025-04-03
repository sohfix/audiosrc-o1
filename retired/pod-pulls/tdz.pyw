#!/usr/bin/env python3
"""
TDZ Updater (prx-style) with Colors & Banner
Hardcoded feed -> G:\TDZ
Shows a progress window for each episode, with speed & ETA,
plus a top banner and stylized color scheme.

Requires:
  pip install feedparser requests
"""

import os
import re
import shutil
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

import feedparser
import requests

# ---------------------------------------------------------------------
#  HARD-CODED SETTINGS
# ---------------------------------------------------------------------
TDZ_FEED_URL = (
    "https://www.omnycontent.com/d/playlist/"
    "e73c998e-6e60-432f-8610-ae210140c5b1/39e934d7-2ddc-4b3e-bc73-ae2b00156363/"
    "ab6037f4-9a9a-449b-915d-ae2b00156375/podcast.rss"
)
OUTPUT_DIR = r"G:\TDZ"

HTTP_TIMEOUT = 10
MAX_RETRIES = 3
INITIAL_BACKOFF = 2

# ---------------------------------------------------------------------
#  HELPER FUNCTIONS
# ---------------------------------------------------------------------
def human_speed(bps: float) -> str:
    """Return a readable speed string (B/s, KB/s, MB/s)."""
    if bps < 1024:
        return f"{bps:.2f} B/s"
    elif bps < 1024 * 1024:
        return f"{bps/1024:.2f} KB/s"
    else:
        return f"{bps/(1024*1024):.2f} MB/s"

def safe_title(txt: str) -> str:
    """Sanitize the episode title for a filename."""
    return "".join(c for c in txt if c.isalnum() or c in " _-").strip()

def ensure_output_dir(path: str):
    """Create folder or raise if it fails."""
    try:
        os.makedirs(path, exist_ok=True)
    except Exception as e:
        raise RuntimeError(f"Cannot create {path}: {e}")

def is_incomplete(file_path: str, remote_size: int) -> bool:
    """
    If remote_size > 0 and local file is significantly smaller,
    consider it incomplete.
    """
    if not os.path.exists(file_path):
        return True
    if remote_size <= 0:
        return False
    local_size = os.path.getsize(file_path)
    # small tolerance:
    TOLERANCE = 1_000_000  # 1 MB
    return (local_size + TOLERANCE) < remote_size

# ---------------------------------------------------------------------
#  DOWNLOAD PROGRESS WINDOW
# ---------------------------------------------------------------------
class DownloadProgress(tk.Toplevel):
    """
    A single window reused for each episode.
    - If total_size=0 => "indeterminate" (just show MB downloaded)
    - Else => determinate bar with %
    We style it with a nicer background & bigger fonts.
    """

    def __init__(self, parent, total_eps: int, bg_color="#2D2D2D", fg_color="#FFFFFF"):
        super().__init__(parent)
        self.title("Updating TDZ...")
        self.total_eps = total_eps
        self.cancelled = False
        self.is_indeterminate = False

        # Make it modal-like
        self.grab_set()

        # Set geometry
        self.geometry("500x350")
        # Apply color
        self.config(bg=bg_color)

        # Store references to colors for labels
        self.bg_color = bg_color
        self.fg_color = fg_color

        # A style specifically for our labels within this Toplevel
        self.local_style = ttk.Style(self)
        self.local_style.configure(
            "ProgressLabel.TLabel",
            font=("Helvetica", 11),
            background=bg_color,
            foreground=fg_color
        )

        self.progress_var = tk.DoubleVar()

        self.current_label = ttk.Label(self, text="Preparing downloads...", style="ProgressLabel.TLabel")
        self.current_label.pack(padx=10, pady=10)

        self.disk_label = ttk.Label(self, text="", style="ProgressLabel.TLabel")
        self.disk_label.pack(padx=10, pady=2)

        self.progress_bar = ttk.Progressbar(self, length=400, variable=self.progress_var)
        self.progress_bar.pack(padx=10, pady=10)

        self.speed_label = ttk.Label(self, text="", style="ProgressLabel.TLabel")
        self.speed_label.pack(padx=10, pady=2)

        self.time_label = ttk.Label(self, text="", style="ProgressLabel.TLabel")
        self.time_label.pack(padx=10, pady=2)

        self.bytes_label = ttk.Label(self, text="", style="ProgressLabel.TLabel")
        self.bytes_label.pack(padx=10, pady=2)

        self.cancel_btn = ttk.Button(self, text="Cancel", command=self.on_cancel)
        self.cancel_btn.pack(pady=10)

    def on_cancel(self):
        self.cancelled = True

    def start_indeterminate(self):
        self.is_indeterminate = True
        self.progress_bar.config(mode="indeterminate")
        self.progress_bar.start(50)

    def start_determinate(self):
        self.is_indeterminate = False
        self.progress_bar.config(mode="determinate", maximum=100)
        self.progress_bar.stop()
        self.progress_var.set(0)

    def update_info(self, index: int, title: str, total_size: int):
        """Set episode label, disk usage, etc."""
        size_str = f"{total_size/(1024*1024):.1f} MB" if total_size>0 else "Unknown"
        self.current_label.config(
            text=(f"Downloading {index}/{self.total_eps}:\n"
                  f"{title}\nSize: {size_str}")
        )
        # Show disk usage
        try:
            usage = shutil.disk_usage(OUTPUT_DIR)
            free_gb = usage.free / (1024**3)
            total_gb = usage.total / (1024**3)
            self.disk_label.config(
                text=f"Disk: {free_gb:.1f} GB free / {total_gb:.1f} GB total"
            )
        except Exception as e:
            self.disk_label.config(text=f"Disk usage error: {e}")

        # Clear old
        self.speed_label.config(text="")
        self.time_label.config(text="")
        self.bytes_label.config(text="")
        self.update_idletasks()

    def update_progress(self, downloaded: int, total_bytes: int, elapsed: float):
        if self.is_indeterminate:
            # Just show how much downloaded
            mb = downloaded/(1024*1024)
            self.bytes_label.config(text=f"Downloaded: {mb:.1f} MB")
            spd = downloaded / elapsed if elapsed else 0
            self.speed_label.config(text=f"Speed: {human_speed(spd)}")
            self.time_label.config(text="Time left: Unknown")
        else:
            if total_bytes>0:
                pct = (downloaded / total_bytes) * 100
            else:
                pct = 0
            self.progress_var.set(pct)
            spd = downloaded / elapsed if elapsed else 0
            self.speed_label.config(text=f"Speed: {human_speed(spd)}")

            if spd>0 and total_bytes>0:
                remain = (total_bytes - downloaded)/spd
                if remain<60:
                    self.time_label.config(text=f"Est. time: {remain:.1f} sec")
                else:
                    self.time_label.config(text=f"Est. time: {remain/60:.1f} min")
            else:
                self.time_label.config(text="Time left: ...")
        self.update_idletasks()

# ---------------------------------------------------------------------
#  MAIN DOWNLOAD LOGIC
# ---------------------------------------------------------------------
def do_update_tdz(gui_app: "TDZGUI"):
    """Main feed update: parse feed, loop episodes, show progress, etc."""
    gui_app.log("Fetching TDZ feed...")

    # 1) Ensure output dir
    try:
        ensure_output_dir(OUTPUT_DIR)
    except RuntimeError as e:
        messagebox.showerror("Error", str(e))
        return

    # 2) Parse feed
    feed = feedparser.parse(TDZ_FEED_URL)
    if not feed.entries:
        gui_app.log("No episodes found in feed!")
        return

    episodes = feed.entries
    total_ep = len(episodes)
    gui_app.log(f"Found {total_ep} episodes in the feed.")

    # 3) Single progress window for the entire feed
    prog_win = DownloadProgress(gui_app, total_eps=total_ep,
                                bg_color=gui_app.bg_color, fg_color=gui_app.fg_color)

    for idx, ep in enumerate(episodes, start=1):
        if prog_win.cancelled:
            gui_app.log("Update cancelled by user.")
            break

        title = ep.title
        if not ep.enclosures:
            gui_app.log(f"Skipping '{title}' (no enclosures).")
            continue

        enclosure = ep.enclosures[0]
        feed_len = 0
        try:
            feed_len = int(enclosure.get("length","0"))
        except:
            pass

        mp3_url = enclosure.href
        fname = safe_title(title) + ".mp3"
        outpath = os.path.join(OUTPUT_DIR, fname)

        # Check if incomplete or missing
        if os.path.exists(outpath) and not is_incomplete(outpath, feed_len):
            gui_app.log(f"Already have '{title}' => skipping.")
            continue
        if os.path.exists(outpath):
            os.remove(outpath)

        # HEAD to see real total size
        total_bytes = 0
        try:
            r = requests.head(mp3_url, timeout=HTTP_TIMEOUT)
            r.raise_for_status()
            if "Content-Length" in r.headers:
                total_bytes = int(r.headers["Content-Length"])
        except:
            total_bytes = 0

        # 4) Update progress info
        prog_win.update_info(idx, title, total_bytes)
        if total_bytes<=0:
            prog_win.start_indeterminate()
        else:
            prog_win.start_determinate()

        # 5) Download
        success = download_one_file(gui_app, mp3_url, outpath, total_bytes, prog_win)
        if success:
            gui_app.log(f"✔ {title}")
        else:
            gui_app.log(f"✘ Failed {title}")
            break

    prog_win.destroy()
    gui_app.log("Update TDZ done.")


def download_one_file(
    gui_app: "TDZGUI",
    url: str,
    outpath: str,
    total_size: int,
    prog_win: DownloadProgress
) -> bool:
    """Downloads the file with chunked approach, updating the progress window."""
    for attempt in range(1, MAX_RETRIES+1):
        start_t = time.time()
        downloaded = 0
        try:
            with requests.get(url, stream=True, timeout=HTTP_TIMEOUT) as resp:
                resp.raise_for_status()
                with open(outpath, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        if prog_win.cancelled:
                            return False
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                        elapsed = time.time() - start_t
                        prog_win.update_progress(downloaded, total_size, elapsed)
            return True
        except Exception as e:
            gui_app.log(f"Error attempt {attempt} for {url}: {e}")
            time.sleep(INITIAL_BACKOFF*(2**(attempt-1)))
    return False

# ---------------------------------------------------------------------
#  MAIN GUI
# ---------------------------------------------------------------------
class TDZGUI(tk.Tk):
    """A prx-style minimal GUI to 'Update TDZ' only, with a banner & color scheme."""

    def __init__(self):
        super().__init__()
        self.title("TDZ Updater")
        self.geometry("900x600")

        # Choose a color scheme
        self.bg_color = "#1E1E1E"
        self.fg_color = "#FFFFFF"

        # Set up overall style
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            "TLabel",
            font=("Helvetica", 10),
            background=self.bg_color,
            foreground=self.fg_color
        )
        style.configure(
            "TButton",
            font=("Helvetica", 10, "bold"),
            background="#3A3A3A",
            foreground="#FFFFFF"
        )

        # Make the main window background
        self.config(bg=self.bg_color)

        # Attempt to load a banner image (e.g. "tdz_banner.png")
        # You can remove or replace if you don't have it
        self.banner_img = None
        if os.path.exists("../tdz_banner.png"):
            self.banner_img = tk.PhotoImage(file="../tdz_banner.png")

        self.create_widgets()
        self.log("The Daily Zeitgeist podcast update tool.")
        self.log("Welcome...")


    def create_widgets(self):
        # Top frame with a banner (if we have an image)
        banner_frame = tk.Frame(self, bg=self.bg_color)
        banner_frame.pack(side=tk.TOP, fill=tk.X)

        if self.banner_img:
            banner_label = tk.Label(
                banner_frame,
                image=self.banner_img,
                bg=self.bg_color
            )
            banner_label.pack(pady=5)

        # Then a button row
        btn_frame = tk.Frame(self, bg=self.bg_color)
        btn_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=10)

        btn_update = ttk.Button(btn_frame, text="Enjoy the Zeit", command=self.on_update)
        btn_update.pack(side=tk.LEFT, padx=5)

        btn_about = ttk.Button(btn_frame, text="About", command=self.on_about)
        btn_about.pack(side=tk.LEFT, padx=5)

        btn_exit = ttk.Button(btn_frame, text="Exit", command=self.quit)
        btn_exit.pack(side=tk.LEFT, padx=5)

        # The log area
        self.log_text = tk.Text(
            self,
            height=20,
            bg="#2D2D2D",
            fg="#FFFFFF",
            font=("Courier New", 10)
        )
        self.log_text.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.log_text.insert(tk.END, "Log:\n")
        self.log_text.config(state=tk.DISABLED)

    def log(self, msg: str):
        """Append a line to the log box."""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"{time.strftime('%H:%M:%S')} - {msg}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def on_update(self):
        """Spawn a background thread to update the feed."""
        t = threading.Thread(target=do_update_tdz, args=(self,), daemon=True)
        t.start()

    def on_about(self):
        messagebox.showinfo(
            "About",
            "."
            "Downloads The Daily Zeitgeist feed into G:\\TDZ,\n"
            "shows progress for each episode.\n"
            "Banner: 'tdz_banner.png' (optional)."
        )

def main():
    app = TDZGUI()
    app.mainloop()

if __name__ == "__main__":
    main()
