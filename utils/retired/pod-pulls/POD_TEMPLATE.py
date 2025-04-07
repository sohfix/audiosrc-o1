#!/usr/bin/env python3
"""
Example "cool" GUI podcast downloader using Dear PyGui.
Reads config from C:\tools\podcast.ini and downloads multiple feeds.

Requires:
  pip install dearpygui feedparser requests
"""

import configparser
import os
import re
import shutil
import threading
import time

import feedparser
import requests

# ---------- TRY IMPORT DEAR PYGGUI -------------
try:
    import dearpygui.dearpygui as dpg
except ImportError as e:
    raise SystemExit("Dear PyGui not installed. Please run: pip install dearpygui") from e

# -------------- GLOBAL CONFIG / SETTINGS --------------
CONFIG_PATH = r"C:\tools\podcast.ini"
config = None

# Our data structure to hold each podcast's:
# {
#   'feed_url': '...',
#   'short_name': '...',
#   'output_dir': '...',
#   'progress_bar_id': ...,
#   'status_text_id': ...,
#   'total_episodes': ...,
#   'downloaded_count': ...
# }
podcast_entries = []

# We store a global log buffer to update the “Log” text widget
LOG_BUFFER = ""

# -------------- LOAD CONFIG --------------
def load_config():
    global config
    parser = configparser.ConfigParser()
    parser.read(CONFIG_PATH)
    config = parser  # store globally

    if not parser.has_section("system"):
        raise RuntimeError("Invalid config file: missing [system] section.")
    if not parser.has_section("Podcasts"):
        raise RuntimeError("Invalid config file: missing [Podcasts] section.")

    # Build podcast list from the single line in config
    raw_list = parser["Podcasts"].get("podcast_list", "").strip()
    # Format is:   url : shortname : outdir ; url : shortname : outdir ; ...
    # Split by semicolons
    parts = [chunk.strip() for chunk in raw_list.split(";") if chunk.strip()]
    for chunk in parts:
        # chunk = "url : shortname : outdir"
        sub = [x.strip() for x in chunk.split(":")]
        if len(sub) < 3:
            continue
        feed_url, short_name, outdir = sub[0], sub[1], sub[2]
        podcast_entries.append({
            "feed_url": feed_url,
            "short_name": short_name,
            "output_dir": outdir,
            "progress_bar_id": None,
            "status_text_id": None,
            "total_episodes": 0,
            "downloaded_count": 0,
        })

# -------------- UTILITY / HELPERS --------------
def log(msg: str):
    """Append to our global log buffer, update the DPG text widget."""
    global LOG_BUFFER
    timestamp = time.strftime("%H:%M:%S")
    LOG_BUFFER += f"[{timestamp}] {msg}\n"
    # set_value is safe to call from any thread in newer dearpygui versions, but
    # if you have concurrency issues, you might post it via callback queue
    dpg.set_value("log_text", LOG_BUFFER)
    # also auto-scroll if desired
    dpg.set_y_scroll("log_window", dpg.get_y_scroll_max("log_window"))

def human_speed(bps: float) -> str:
    if bps < 1024:
        return f"{bps:.2f} B/s"
    elif bps < 1024 * 1024:
        return f"{bps/1024:.2f} KB/s"
    else:
        return f"{bps/(1024*1024):.2f} MB/s"

def safe_title(txt: str) -> str:
    """Sanitize the episode title for a filename."""
    return "".join(c for c in txt if c.isalnum() or c in " _-").strip()

def is_incomplete(file_path: str, remote_size: int) -> bool:
    """If local file significantly smaller than remote_size => incomplete."""
    if not os.path.exists(file_path):
        return True
    if remote_size <= 0:
        return False
    local_size = os.path.getsize(file_path)
    # Tolerance from config
    tolerance_bytes = 1024*1024*config["system"].getint("tolerance_mb", 1)
    return (local_size + tolerance_bytes) < remote_size

# -------------- PODCAST DOWNLOAD THREADS --------------
def download_podcast(podcast: dict):
    """
    Downloads all missing/incomplete episodes for the given feed
    and updates the progress bar/status in the GUI.
    Runs in a background thread.
    """
    feed_url = podcast["feed_url"]
    out_dir = podcast["output_dir"]
    short_name = podcast["short_name"]
    pb_id = podcast["progress_bar_id"]
    st_id = podcast["status_text_id"]

    # read system config
    download_timeout = config["system"].getint("download_timeout", 5)
    max_retries = config["system"].getint("max_retries", 3)
    initial_retry_backoff = config["system"].getint("initial_retry_backoff", 2)

    # 1) Ensure output dir
    try:
        os.makedirs(out_dir, exist_ok=True)
    except Exception as e:
        log(f"[{short_name}] Cannot create output dir: {e}")
        return

    # 2) Parse feed
    try:
        feed = feedparser.parse(feed_url)
    except Exception as e:
        log(f"[{short_name}] feed parse error: {e}")
        return

    if not feed.entries:
        log(f"[{short_name}] No entries in feed.")
        return

    episodes = feed.entries
    total_ep = len(episodes)
    podcast["total_episodes"] = total_ep
    log(f"[{short_name}] Found {total_ep} episodes.")

    # We'll iterate episodes newest to oldest or oldest to newest, your call
    # Here we keep feed order:
    count_downloaded = 0

    # We'll store these to let user see a combined feed progress (0.0->1.0)
    for idx, ep in enumerate(episodes, start=1):
        # If user closes the app there's no direct "cancel" here,
        # but we can break if needed. We'll keep going for now.

        title = ep.title
        if not ep.enclosures:
            log(f"[{short_name}] Skip '{title}' (no enclosures).")
            continue

        enclosure = ep.enclosures[0]
        feed_len = 0
        try:
            feed_len = int(enclosure.get("length", "0"))
        except:
            pass

        mp3_url = enclosure.href
        fname = safe_title(title) + ".mp3"
        outpath = os.path.join(out_dir, fname)

        # Check if incomplete or missing
        if os.path.exists(outpath) and not is_incomplete(outpath, feed_len):
            # already have
            dpg.configure_item(st_id, default_value=f"Skipping: {title[:60]}...")
            continue
        if os.path.exists(outpath):
            # remove partial
            os.remove(outpath)

        # HEAD to see real total size if possible
        total_bytes = 0
        try:
            # requests head
            r = requests.head(mp3_url, timeout=download_timeout)
            if r.status_code < 400 and "Content-Length" in r.headers:
                total_bytes = int(r.headers["Content-Length"])
        except:
            pass

        # Download attempts
        success = False
        for attempt in range(1, max_retries + 1):
            start_t = time.time()
            downloaded = 0
            chunk_size = 8192
            try:
                dpg.configure_item(st_id, default_value=f"Downloading: {title[:50]}... (try {attempt}/{max_retries})")
                with requests.get(mp3_url, stream=True, timeout=download_timeout) as resp:
                    resp.raise_for_status()
                    with open(outpath, "wb") as f:
                        for chunk in resp.iter_content(chunk_size=chunk_size):
                            if not chunk:
                                continue
                            f.write(chunk)
                            downloaded += len(chunk)
                            elapsed = time.time() - start_t

                            # update feed progress bar (roughly)
                            # feed-level progress -> (episode_index + fraction_of_episode) / total_episodes
                            fraction_of_ep = (downloaded / total_bytes) if total_bytes > 0 else 0
                            overall_progress = (idx - 1 + fraction_of_ep) / total_ep
                            dpg.configure_item(pb_id, default_value=overall_progress)

                            # optionally update status text with speed
                            spd = downloaded / elapsed if elapsed else 0
                            status_txt = f"Downloading: {title[:30]}... {human_speed(spd)}"
                            dpg.configure_item(st_id, default_value=status_txt)

                success = True
                break
            except Exception as e:
                log(f"[{short_name}] Error on attempt {attempt}: {e}")
                time.sleep(initial_retry_backoff * (2 ** (attempt - 1)))

        if success:
            count_downloaded += 1
            log(f"[{short_name}] Done: {title}")
        else:
            log(f"[{short_name}] Failed: {title}")
            break  # or continue if you want to keep going on failure

    # final
    dpg.configure_item(pb_id, default_value=1.0)  # done
    log(f"[{short_name}] Download complete. ({count_downloaded}/{total_ep} new)")

def download_all_feeds():
    """Spins up a thread for each feed, or does them sequentially. We'll do them sequentially for clarity."""
    for podcast in podcast_entries:
        # reset the progress bar & status
        if podcast["progress_bar_id"] is not None:
            dpg.configure_item(podcast["progress_bar_id"], default_value=0.0)
        if podcast["status_text_id"] is not None:
            dpg.configure_item(podcast["status_text_id"], default_value="Pending...")

    for podcast in podcast_entries:
        download_podcast(podcast)

    log("All feeds done.")

def on_download_all_callback():
    # run the downloads in a separate thread so the GUI won't block
    threading.Thread(target=download_all_feeds, daemon=True).start()

def show_about():
    dpg.show_item("about_window")

def quit_app():
    dpg.stop_dearpygui()

# -------------- CREATE GUI --------------
def create_gui():
    dpg.create_context()

    # Optionally check config for dark_mode
    dm_value = config["system"].get("dark_mode", "TOGGLE").lower()
    if dm_value.startswith("t"):
        dpg.configure_app(init_file="", docking=False)
        dpg.create_viewport(title="Podcast Downloader (Dark Mode)", width=1000, height=700)
        dpg.setup_dearpygui()
        dpg.set_viewport_vsync(True)
        dpg.show_viewport()
        dpg.set_global_font_scale(1.05)
        dpg.toggle_viewport_fullscreen()  # just for "flashiness" if desired
        dpg.configure_app(manual_callback_management=False)
        dpg.set_theme_color(dpg.mvThemeCol_WindowBg, (32, 32, 32, 255))
    else:
        dpg.create_viewport(title="Podcast Downloader", width=1000, height=700)
        dpg.setup_dearpygui()
        dpg.show_viewport()

    with dpg.window(label="Podcast Downloader", tag="main_window", width=1000, height=700):
        dpg.add_text("Welcome to the DearPyGui Podcast Downloader!")
        dpg.add_spacer()
        dpg.add_button(label="Download All", callback=on_download_all_callback)
        dpg.add_same_line()
        dpg.add_button(label="About", callback=show_about)
        dpg.add_same_line()
        dpg.add_button(label="Quit", callback=quit_app)

        dpg.add_separator()
        dpg.add_text("Podcast Feeds:")

        # We'll create a child window or child viewport to hold a table
        with dpg.child_window(width=-1, height=250):
            with dpg.table(header_row=True, resizable=True, borders_innerH=True, borders_innerV=True,
                           row_background=True, policy=dpg.mvTable_SizingStretchProp):
                dpg.add_table_column(label="Feed Name")
                dpg.add_table_column(label="Feed URL")
                dpg.add_table_column(label="Output Folder")
                dpg.add_table_column(label="Progress")
                dpg.add_table_column(label="Status")

                for podcast in podcast_entries:
                    with dpg.table_row():
                        dpg.add_text(podcast["short_name"])
                        dpg.add_text(podcast["feed_url"])
                        dpg.add_text(podcast["output_dir"])

                        pb_id = f"pb_{podcast['short_name']}"
                        st_id = f"st_{podcast['short_name']}"

                        dpg.add_progress_bar(default_value=0.0, width=200, tag=pb_id)
                        dpg.add_text("Pending...", tag=st_id)

                        podcast["progress_bar_id"] = pb_id
                        podcast["status_text_id"] = st_id

        # Log area
        dpg.add_separator()
        dpg.add_text("Log:")
        with dpg.child_window(width=-1, height=-1, tag="log_window"):
            dpg.add_text("", tag="log_text")

    # About window (hidden by default)
    with dpg.window(label="About", tag="about_window", modal=True, show=False, no_resize=True, autosize=True):
        dpg.add_text("This is a multi-podcast downloader demo.")
        dpg.add_text("Using feedparser + requests + dearpygui.")
        dpg.add_button(label="Close", callback=lambda: dpg.hide_item("about_window"))

    dpg.set_primary_window("main_window", True)

    # Done building context
    dpg.start_dearpygui()
    dpg.destroy_context()

# -------------- MAIN --------------
def main():
    load_config()    # read ini, fill podcast_entries
    create_gui()     # build and run the dearpygui main loop

if __name__ == "__main__":
    main()
