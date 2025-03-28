#!/usr/bin/env python3
"""
prx 2.2.0 [All Settings in INI + Window Resizing + Tolerance in MB]

CHANGELOG:
  - All configurable settings are now read from the INI.
  - The damaged-file tolerance is specified in MB
  - Window size (width x height) is read from the INI and applied (Windows only).
  - You can change any setting (timeouts, retries, tolerance, window size, etc.) via the INI.
"""

import configparser
import logging
import os
import re
# import shlex
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, TextIO, Tuple

import feedparser
import httpx
import requests
from rich.console import Console
from rich.panel import Panel
from rich.progress import (BarColumn, Progress, ProgressColumn, TextColumn,
                           TimeElapsedColumn)
from rich.table import Table

console: Console = Console()
QUIET_MODE: bool = False

# Default fallback values (if not present in INI)
DEFAULT_TIMEOUT = 10
DEFAULT_MAX_RETRIES = 3
DEFAULT_INITIAL_BACKOFF = 2
DEFAULT_HTTPS_ONLY = False
DEFAULT_TOLERANCE_MB = 5  # tolerance in MB (5 MB)
DEFAULT_WINDOW_WIDTH = 120
DEFAULT_WINDOW_HEIGHT = 30
DEFAULT_OUTPUT_DIR = r"G:\tools\downloads"
DEFAULT_LOG_DIR = r"G:\tools\logs"

VERSION = "2.2.0 [All Settings in INI + Window Resizing + Tolerance in MB]"

FAILED_DOWNLOADS: List[Dict[str, str]] = []


###############################################################################
#                        Damaged File Check Function                          #
###############################################################################


def is_file_damaged(
    file_path: str,
    enclosure_length: Optional[int],
    mp3_url: Optional[str],
    tolerance: int,
    timeout: int,
    do_head_if_needed: bool = True,
) -> bool:
    """
    Check whether the local MP3 at file_path is incomplete/damaged.

    - If the file doesn't exist, returns True.
    - If a valid enclosure_length (from the feed) is provided (and > 0), uses it.
    - Otherwise, if mp3_url is provided and do_head_if_needed is True, does a HEAD request to get Content-Length.
    - Compares the local file size to (remote_size - tolerance). If local_size is less, returns True.
    - If no valid remote size can be determined, returns False (assumes file is OK).

    :param file_path: Local file path.
    :param enclosure_length: File size from the RSS feed (if available).
    :param mp3_url: The URL for the MP3 (used for HEAD request if needed).
    :param tolerance: Tolerance in bytes (converted from MB setting) for size discrepancies.
    :param timeout: Timeout in seconds for HEAD requests.
    #todo :param do_head_if_needed: Whether to perform a HEAD request if enclosure_length is not valid.
    :return: True if the file is determined to be damaged/incomplete.
    """
    if not os.path.exists(file_path):
        return True

    local_size = os.path.getsize(file_path)
    remote_size: Optional[int] = None

    if enclosure_length and enclosure_length > 0:
        remote_size = enclosure_length

    if remote_size is None and mp3_url and do_head_if_needed:
        try:
            with httpx.Client(http2=True, timeout=timeout) as client:
                head_resp = client.head(mp3_url)
                head_resp.raise_for_status()
                content_len_str = head_resp.headers.get("Content-Length", "")
                if content_len_str.isdigit():
                    possible_size = int(content_len_str)
                    if possible_size > 0:
                        remote_size = possible_size
        except Exception:
            remote_size = None

    if remote_size is None:
        return False

    # todo:
    #
    retol = remote_size - tolerance
    if local_size < retol:
        return True

    return False


###############################################################################
#                              Progress UI                                    #
###############################################################################


class MBPercentColumn(ProgressColumn):
    """A progress column showing MB downloaded and percent complete."""

    def render(self, task) -> str:
        if task.total is None or task.total == 0:
            return "0.00MB/??MB (0%)"
        downloaded_mb = task.completed / (1024 * 1024)
        total_mb = task.total / (1024 * 1024)
        pct = (task.completed / task.total) * 100
        return f"{downloaded_mb:5.2f}MB/{total_mb:5.2f}MB ({pct:5.1f}%)"


###############################################################################
#                          Helper Functions                                   #
###############################################################################


def human_readable_speed(bps: float) -> str:
    """Convert bytes/sec to a human-friendly string."""
    if bps < 1024:
        return f"{bps:.2f} B/s"
    elif bps < 1024 * 1024:
        return f"{bps / 1024:.2f} KB/s"
    else:
        return f"{bps / (1024 * 1024):.2f} MB/s"


def get_extended_server_info(url: str, timeout: int) -> Dict[str, str]:
    """Perform a HEAD request to get extended server info."""
    try:
        with httpx.Client(http2=True, timeout=timeout) as client:
            resp = client.head(url)
            return {
                "Server": resp.headers.get("server", "Unknown"),
                "HTTP Version": resp.http_version,
                "Content-Type": resp.headers.get("content-type", "Unknown"),
                "Content-Length": resp.headers.get("content-length", "Unknown"),
                "Date": resp.headers.get("date", "Unknown"),
            }
    except Exception as e:
        return {"Error": str(e)}


###############################################################################
#                        Config & File Helpers                                #
###############################################################################


def clear_screen() -> None:
    console.clear()


def get_config_path() -> str:
    """Return the path to prx.ini on G:\."""
    return r"G:\tools\prx.ini"


def ensure_output_dir(output_dir: str) -> None:
    """Ensure the output directory exists; create if not."""
    try:
        os.makedirs(output_dir, exist_ok=True)
    except OSError as e:
        console.print(Panel(f"Could not create '{output_dir}': {e}", style="red"))
        sys.exit(1)


def init_config() -> Tuple[configparser.ConfigParser, str]:
    """
    Load or create a default prx.ini at G:\tools\prx.ini.
    This file contains all configurable settings.
    """
    config_path = get_config_path()
    os.makedirs(os.path.dirname(config_path), exist_ok=True)

    config = configparser.ConfigParser()
    if os.path.exists(config_path):
        config.read(config_path)
        if not QUIET_MODE:
            console.print(
                Panel(
                    f"Loaded config from:\n{config_path}", title="Config", style="blue"
                )
            )
    else:
        if not QUIET_MODE:
            console.print(
                Panel(
                    f"No config found. Creating default at:\n{config_path}",
                    title="Config",
                    style="yellow",
                )
            )
        config["user"] = {"name": "", "password": ""}
        config["system"] = {
            "os": "windows",
            "default_output_dir": DEFAULT_OUTPUT_DIR,
            "download_timeout": str(DEFAULT_TIMEOUT),
            "max_retries": str(DEFAULT_MAX_RETRIES),
            "initial_retry_backoff": str(DEFAULT_INITIAL_BACKOFF),
            "https_only": str(DEFAULT_HTTPS_ONLY),
            "quiet_mode": str(QUIET_MODE),
            "tolerance_mb": str(DEFAULT_TOLERANCE_MB),  # tolerance in MB
            "window_width": str(DEFAULT_WINDOW_WIDTH),
            "window_height": str(DEFAULT_WINDOW_HEIGHT),
        }
        config["logging"] = {
            "log_dir": DEFAULT_LOG_DIR,
            "log_level": "INFO",
        }
        config["Podcasts"] = {"podcast_list": ""}
        with open(config_path, "w") as cf:
            config.write(cf)
        if not QUIET_MODE:
            console.print(
                Panel("Default prx.ini created.", title="Config", style="green")
            )
    return config, config_path


def setup_logging() -> None:
    """Set up logging based on config."""
    config, _ = init_config()
    log_dir = config["logging"].get("log_dir", DEFAULT_LOG_DIR)
    level = config["logging"].get("log_level", "INFO")
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    try:
        os.makedirs(log_dir, exist_ok=True)
    except OSError as e:
        console.print(Panel(f"Cannot create log dir '{log_dir}': {e}", style="red"))
        log_dir = ""
    tstamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"session_{tstamp}.log") if log_dir else None
    logging.basicConfig(
        filename=log_file if log_file else None,
        filemode="w",
        format="%(asctime)s - %(levelname)s - %(message)s",
        level=numeric_level,
    )
    if log_file and not QUIET_MODE:
        console.print(Panel(f"Logging to:\n{log_file}", title="Logging", style="green"))
    elif not QUIET_MODE:
        console.print(
            Panel("Logging to console only.", title="Logging", style="yellow")
        )
    logging.info("Logging initialized.")


def validate_config() -> None:
    """Ensure the config has the required user info."""
    config, config_path = init_config()
    changed = False
    if "user" not in config:
        config["user"] = {}
    if not config["user"].get("name"):
        console.print(Panel("No user name in config.", style="yellow"))
        config["user"]["name"] = console.input("[blue]Enter your name: [/blue]")
        changed = True
    if not config["user"].get("password"):
        console.print(Panel("No password in config.", style="yellow"))
        config["user"]["password"] = console.input("[blue]Enter password: [/blue]")
        changed = True
    if changed:
        with open(config_path, "w") as cf:
            config.write(cf)
        console.print(Panel("Config updated!", style="green"))
    else:
        console.print(Panel("Config is fine.", style="green"))


def set_window_size(config: configparser.ConfigParser) -> None:
    """
    Adjust the console window size based on the config settings.
    Works only on Windows.
    """
    try:
        import platform

        if platform.system().lower() != "windows":
            return
        width = int(config["system"].get("window_width", DEFAULT_WINDOW_WIDTH))
        height = int(config["system"].get("window_height", DEFAULT_WINDOW_HEIGHT))
        os.system(f"mode con: cols={width} lines={height}")
    except Exception as e:
        console.print(Panel(f"Failed to set window size: {e}", style="red"))


###############################################################################
#                  Podcast List Management Functions                          #
###############################################################################


def manage_podcasts_in_config() -> None:
    """
    Manage the [Podcasts] section in prx.ini.
    Format: PODCAST_LINK : NAME_ID : OUTPUT_DIRECTORY (semicolon-separated).
    """
    config, config_path = init_config()
    while True:
        console.print(
            Panel(
                "Manage Podcasts:\n"
                "1) View list\n"
                "2) Add a new one\n"
                "3) Edit existing\n"
                "4) Remove\n"
                "5) Return",
                title="Podcast List",
                style="cyan",
            )
        )
        choice = console.input("Choice: ").strip()
        p_line = config["Podcasts"].get("podcast_list", "").strip()
        entries = [ch.strip() for ch in p_line.split(";") if ch.strip()]
        triplets: List[Tuple[str, str, str]] = []
        for e in entries:
            parts = [p.strip() for p in e.split(" : ")]
            if len(parts) == 3:
                triplets.append((parts[0], parts[1], parts[2]))
        if choice == "1":
            if not triplets:
                console.print(Panel("No podcasts.", style="yellow"))
            else:
                t = Table(title="Podcast List")
                t.add_column("NAME_ID", style="cyan")
                t.add_column("Link", style="magenta")
                t.add_column("Output Dir", style="green")
                for link, n_id, outd in triplets:
                    t.add_row(n_id, link, outd)
                console.print(t)
        elif choice == "2":
            new_p = console.input("LINK : NAME_ID : OUTPUT_DIR: ").strip()
            p_parts = [x.strip() for x in new_p.split(" : ")]
            if len(p_parts) == 3:
                triplets.append((p_parts[0], p_parts[1], p_parts[2]))
                new_str = " ; ".join(f"{l} : {n} : {o}" for (l, n, o) in triplets)
                config["Podcasts"]["podcast_list"] = new_str
                with open(config_path, "w") as cf:
                    config.write(cf)
                console.print(Panel(f"Added '{p_parts[1]}'", style="green"))
            else:
                console.print(Panel("Invalid format.", style="red"))
        elif choice == "3":
            if not triplets:
                console.print(Panel("No podcasts to edit.", style="yellow"))
                continue
            for i, (l, n, o) in enumerate(triplets, 1):
                console.print(f"{i}) {n} -> {l} | {o}")
            sel = console.input("Which number to edit: ").strip()
            try:
                idx = int(sel)
                if 1 <= idx <= len(triplets):
                    old_l, old_n, old_o = triplets[idx - 1]
                    console.print(Panel(f"Editing '{old_n}'", style="blue"))
                    new_v = console.input(
                        "New LINK : NAME_ID : OUT_DIR (blank=skip): "
                    ).strip()
                    if new_v:
                        p2 = [p.strip() for p in new_v.split(" : ")]
                        if len(p2) == 3:
                            triplets[idx - 1] = (p2[0], p2[1], p2[2])
                        else:
                            console.print(Panel("Bad format. Skipping.", style="red"))
                            continue
                    final_str = " ; ".join(f"{l} : {n} : {o}" for (l, n, o) in triplets)
                    config["Podcasts"]["podcast_list"] = final_str
                    with open(config_path, "w") as cf:
                        config.write(cf)
                    console.print(Panel("Podcast updated.", style="green"))
                else:
                    console.print(Panel("Invalid selection.", style="red"))
            except ValueError:
                console.print(Panel("Enter a number.", style="red"))
        elif choice == "4":
            if not triplets:
                console.print(Panel("No podcasts to remove.", style="yellow"))
                continue
            for i, (l, n, o) in enumerate(triplets, 1):
                console.print(f"{i}) {n} -> {l} | {o}")
            sel = console.input("Number to remove: ").strip()
            try:
                idx = int(sel)
                if 1 <= idx <= len(triplets):
                    removed = triplets.pop(idx - 1)
                    final_str = " ; ".join(f"{l} : {n} : {o}" for (l, n, o) in triplets)
                    config["Podcasts"]["podcast_list"] = final_str
                    with open(config_path, "w") as cf:
                        config.write(cf)
                    console.print(Panel(f"Removed '{removed[1]}'", style="green"))
                else:
                    console.print(Panel("Invalid selection.", style="red"))
            except ValueError:
                console.print(Panel("Enter a number.", style="red"))
        elif choice == "5":
            break
        else:
            console.print(Panel("Invalid choice.", style="red"))


def parse_podcast_list(config: configparser.ConfigParser) -> List[Tuple[str, str, str]]:
    """Parse the podcast_list from [Podcasts] section."""
    line = config["Podcasts"].get("podcast_list", "").strip()
    if not line:
        return []
    chunks = [c.strip() for c in line.split(";") if c.strip()]
    results = []
    for ch in chunks:
        parts = [p.strip() for p in ch.split(" : ")]
        if len(parts) == 3:
            results.append((parts[0], parts[1], parts[2]))
    return results


###############################################################################
#                        Main Command Handlers                                #
###############################################################################


def handle_init_command() -> None:
    """Initialize config on G:\ and prompt for user info."""
    console.print(Panel("Running init for G:\\ environment.", style="blue"))
    config, _ = init_config()
    validate_config()
    set_window_size(config)
    console.print(Panel("Init complete!", style="green"))


def manage_settings_config() -> None:
    """View or edit prx.ini on G:\."""
    config, config_path = init_config()
    console.print(Panel("Settings management.", style="blue"))
    action = console.input("Choose (view/edit): ").strip().lower()
    if action == "view":
        if os.path.exists(config_path):
            with open(config_path, "r") as cfile:
                cdata = cfile.read()
            console.print(Panel(cdata, title="prx.ini", style="blue"))
        else:
            console.print(Panel("No config found!", style="red"))
    elif action == "edit":
        validate_config()
        adv = console.input("Edit advanced settings? (y/n): ").strip().lower()
        if adv == "y":
            changed = False
            config, config_path = init_config()
            current_out = config["system"].get("default_output_dir", DEFAULT_OUTPUT_DIR)
            new_out = console.input(
                f"Current output dir: {current_out}\nNew? (blank=skip): "
            ).strip()
            if new_out:
                config["system"]["default_output_dir"] = new_out
                changed = True

            current_log_dir = config["logging"].get("log_dir", DEFAULT_LOG_DIR)
            new_log_dir = console.input(
                f"Current log dir: {current_log_dir}\nNew? (blank=skip): "
            ).strip()
            if new_log_dir:
                config["logging"]["log_dir"] = new_log_dir
                changed = True

            current_lvl = config["logging"].get("log_level", "INFO")
            new_lvl = (
                console.input(
                    f"Current log level: {current_lvl}\n(DEBUG/INFO/WARNING/ERROR/CRITICAL) blank=skip: "
                )
                .strip()
                .upper()
            )
            valids = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
            if new_lvl and new_lvl in valids:
                config["logging"]["log_level"] = new_lvl
                changed = True

            # Allow changing window size and tolerance too:
            current_tolerance = config["system"].get(
                "tolerance_mb", str(DEFAULT_TOLERANCE_MB)
            )
            new_tol = console.input(
                f"Current tolerance (MB): {current_tolerance}\nNew? (blank=skip): "
            ).strip()
            if new_tol:
                config["system"]["tolerance_mb"] = new_tol
                changed = True

            current_width = config["system"].get(
                "window_width", str(DEFAULT_WINDOW_WIDTH)
            )
            new_width = console.input(
                f"Current window width: {current_width}\nNew? (blank=skip): "
            ).strip()
            if new_width:
                config["system"]["window_width"] = new_width
                changed = True

            current_height = config["system"].get(
                "window_height", str(DEFAULT_WINDOW_HEIGHT)
            )
            new_height = console.input(
                f"Current window height: {current_height}\nNew? (blank=skip): "
            ).strip()
            if new_height:
                config["system"]["window_height"] = new_height
                changed = True

            if changed:
                with open(config_path, "w") as cf:
                    config.write(cf)
                console.print(Panel("Config updated.", style="green"))
            else:
                console.print(Panel("No changes.", style="green"))
    else:
        console.print(Panel("Invalid action.", style="red"))


def download_with_progress(
    url: str,
    output_path: str,
    description: str = "Downloading",
    verbose: bool = False,
    timeout: int = DEFAULT_TIMEOUT,
    max_retries: int = DEFAULT_MAX_RETRIES,
    initial_backoff: int = DEFAULT_INITIAL_BACKOFF,
) -> bool:
    """
    Download a file while showing a progress bar.
    Returns True on success, False after retries.
    """
    if verbose:
        info = get_extended_server_info(url, timeout)
        msg = "\n".join(f"{k}: {v}" for k, v in info.items())
        console.print(Panel(f"Server Info:\n{msg}", style="cyan"))
    for attempt in range(1, max_retries + 1):
        start_t = time.time()
        try:
            config, _ = init_config()
            https_only = config["system"].getboolean(
                "https_only", fallback=DEFAULT_HTTPS_ONLY
            )
            if https_only and not url.lower().startswith("https"):
                raise requests.RequestException("HTTP not allowed in https_only mode.")
            resp = requests.get(url, stream=True, timeout=timeout)
            resp.raise_for_status()
            total_size = int(resp.headers.get("content-length", 0))
            with open(output_path, "wb") as f, Progress(
                TextColumn("[bold blue]{task.description}[/bold blue]"),
                BarColumn(),
                MBPercentColumn(),
                TimeElapsedColumn(),
                console=console,
                transient=QUIET_MODE,
            ) as progress:
                task = progress.add_task(description, total=total_size)
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        progress.update(task, advance=len(chunk))
            elapsed = time.time() - start_t
            speed = total_size / elapsed if elapsed else 0
            if verbose:
                console.print(
                    Panel(
                        f"Downloaded in {elapsed:.2f}s at {human_readable_speed(speed)}",
                        style="green",
                    )
                )
            logging.info(f"Downloaded: {url} -> {output_path}")
            return True
        except requests.Timeout:
            console.print(
                Panel(
                    f"Timeout {attempt}/{max_retries}: {url}",
                    title="Timeout",
                    style="red",
                )
            )
            logging.exception(f"Timeout {attempt} for {url}")
        except Exception as e:
            console.print(
                Panel(
                    f"Error {attempt}/{max_retries} for {url}\n{e}",
                    title="Download Error",
                    style="red",
                )
            )
            logging.exception(f"Error {attempt} for {url}")
        backoff = initial_backoff * (2 ** (attempt - 1))
        time.sleep(backoff)
    return False


def build_episode_filename(original_title: str, fmt: str) -> str:
    """
    Return a sanitized filename (without extension) based on the episode title.
    If fmt is 'daily' and the title ends with 6 digits, move them to the front.
    """

    def sanitize(txt: str) -> str:
        return "".join(c for c in txt if c.isalnum() or c in " _-").rstrip()

    if fmt == "daily":
        pattern = r"^(.*)\s+(\d{6})$"
        m = re.match(pattern, original_title)
        if m:
            main_part, date_part = m.groups()
            return f"{date_part} {sanitize(main_part)}".strip()
        return sanitize(original_title)
    else:
        return sanitize(original_title)


def download_podcast_rss(
    rss_url: str,
    output_dir: str,
    count: Optional[int] = None,
    searchby: Optional[str] = None,
    verbose: bool = False,
    oldest_first: bool = False,
    format_str: str = "default",
) -> None:
    """
    Download episodes from an RSS feed.
    If a local file exists, check if it's damaged using is_file_damaged().
    If it's damaged, remove and re-download. Otherwise, skip.
    """
    logging.info(
        f"Download from {rss_url}, dir={output_dir}, count={count}, search={searchby}, oldest={oldest_first}, fmt={format_str}"
    )
    if verbose:
        console.print(
            Panel(f"RSS: {rss_url}\nOut: {output_dir}\nFmt: {format_str}", style="blue")
        )
    ensure_output_dir(output_dir)
    config, _ = init_config()
    # Read tolerance (in MB) from config, convert to bytes:
    try:
        tol_mb = float(config["system"].get("tolerance_mb", str(DEFAULT_TOLERANCE_MB)))
    except ValueError:
        tol_mb = DEFAULT_TOLERANCE_MB
    tolerance = int(tol_mb * 1024 * 1024)
    # Read timeout from config:
    try:
        timeout = int(config["system"].get("download_timeout", str(DEFAULT_TIMEOUT)))
    except ValueError:
        timeout = DEFAULT_TIMEOUT

    feed = feedparser.parse(rss_url)
    if not feed.entries:
        console.print(Panel("No episodes found in feed.", style="yellow"))
        return
    entries = (
        [e for e in feed.entries if (searchby.lower() in e.title.lower())]
        if searchby
        else feed.entries
    )
    if not entries:
        console.print(Panel(f"No episodes match '{searchby}'.", style="yellow"))
        return

    def get_date(e: Any) -> Optional[float]:
        if hasattr(e, "published_parsed") and e.published_parsed:
            return time.mktime(e.published_parsed)
        if hasattr(e, "updated_parsed") and e.updated_parsed:
            return time.mktime(e.updated_parsed)
        return None

    with_time = []
    without_time = []
    for ep in entries:
        dt = get_date(ep)
        if dt is not None:
            with_time.append((ep, dt))
        else:
            without_time.append(ep)
    with_time.sort(key=lambda x: x[1], reverse=(not oldest_first))
    sorted_eps = (
        [ep for (ep, _) in with_time] + without_time
        if oldest_first
        else without_time + [ep for (ep, _) in with_time]
    )
    to_download = sorted_eps[:count] if count else sorted_eps
    if not to_download:
        console.print(
            Panel("No episodes left after sorting/filtering.", style="yellow")
        )
        return
    for idx, ep in enumerate(to_download, start=1):
        title = ep.title
        if not ep.enclosures:
            console.print(
                Panel(f"'{title}' has no enclosure link. Skipping.", style="yellow")
            )
            continue
        enclosure_url = ep.enclosures[0].href
        try:
            feed_len = int(ep.enclosures[0].get("length", "0"))
            if feed_len <= 0:
                feed_len = None
        except ValueError:
            feed_len = None
        base_name = build_episode_filename(title, format_str)
        file_path = os.path.join(output_dir, f"{base_name}.mp3")
        if os.path.exists(file_path):
            damaged = is_file_damaged(
                file_path,
                enclosure_length=feed_len,
                mp3_url=enclosure_url,
                tolerance=tolerance,
                timeout=timeout,
            )
            if not damaged:
                console.print(
                    Panel(
                        f"SKIPPING: '{file_path}' found & OK.",
                        title="Skip",
                        style="yellow",
                    )
                )
                logging.info(f"Skipping complete file: {file_path}")
                continue
            else:
                console.print(
                    Panel(
                        f"File '{file_path}' is incomplete. Removing & re-downloading...",
                        style="yellow",
                    )
                )
                os.remove(file_path)
        if verbose:
            console.print(
                Panel(
                    f"Downloading:\nTitle: {title}\nURL: {enclosure_url}\nFile: {file_path}",
                    title=f"Episode {idx}/{len(to_download)}",
                    style="blue",
                )
            )
        success = download_with_progress(
            enclosure_url,
            file_path,
            description=f"Episode {idx}/{len(to_download)}",
            verbose=verbose,
            timeout=timeout,
        )
        if success:
            console.print(Panel(f"✔ Downloaded '{title}'", style="green"))
        else:
            console.print(Panel(f"❌ Failed to download '{title}'", style="red"))
            FAILED_DOWNLOADS.append(
                {"title": title, "url": enclosure_url, "output": file_path}
            )
        clear_screen()
    if FAILED_DOWNLOADS:
        fail_list = "\n".join(f"- {f['title']}" for f in FAILED_DOWNLOADS)
        console.print(Panel(f"Failed downloads:\n{fail_list}", style="red"))


def update_podcasts(all_update: bool = True) -> None:
    """Update podcasts from the stored list; check and fix local files using is_file_damaged()."""
    config, _ = init_config()
    shows = parse_podcast_list(config)
    if not shows:
        console.print(Panel("No podcasts in config!", style="yellow"))
        return
    if all_update:
        console.print(Panel("Updating ALL podcasts...", style="magenta"))
        for link, name_id, out_dir in shows:
            console.print(Panel(f"Updating '{name_id}'", style="cyan"))
            download_podcast_rss(link, out_dir, count=None, verbose=True)
        console.print(Panel("All updates done.", style="green"))
    else:
        table = Table(title="Stored Podcasts")
        table.add_column("NAME_ID", style="cyan")
        for _, name, _ in shows:
            table.add_row(name)
        console.print(table)
        raw_in = console.input("Which NAME_ID to update?: ").strip()
        found = [(l, n, o) for (l, n, o) in shows if n.lower() == raw_in.lower()]
        if not found:
            console.print(Panel(f"No match for '{raw_in}'", style="red"))
            return
        link, showname, outd = found[0]
        console.print(Panel(f"Updating '{showname}'...", style="cyan"))
        download_podcast_rss(link, outd, count=None, verbose=True)
        console.print(Panel("Update complete.", style="green"))


###############################################################################
#                                Submenus                                     #
###############################################################################


def menu_settings() -> None:
    while True:
        console.print(
            Panel(
                "[bold]Settings[/bold]\n1) Init (create/load prx.ini)\n2) Manage config (view/edit)\n3) Manage podcasts list\n4) Return",
                style="cyan",
            )
        )
        c = console.input("Choice: ").strip()
        if c == "1":
            handle_init_command()
        elif c == "2":
            manage_settings_config()
        elif c == "3":
            manage_podcasts_in_config()
        elif c == "4":
            break
        else:
            console.print(Panel("Invalid choice.", style="red"))


def menu_about() -> None:
    while True:
        console.print(
            Panel(
                "[bold]About[/bold]\n1) About (version {})\n2) Return".format(VERSION),
                style="cyan",
            )
        )
        ch = console.input("Choice: ").strip()
        if ch == "1":
            console.print(
                Panel(
                    f"prx {VERSION}\nAll settings adjustable via INI.\nWindow size and tolerance (in MB) configurable.",
                    style="green",
                )
            )
        elif ch == "2":
            break
        else:
            console.print(Panel("Invalid choice.", style="red"))


def menu_update() -> None:
    while True:
        console.print(
            Panel(
                "[bold]Update Podcasts[/bold]\n1) Update All\n2) Update One\n3) Return",
                style="magenta",
            )
        )
        c = console.input("Choice: ").strip()
        if c == "1":
            update_podcasts(all_update=True)
        elif c == "2":
            update_podcasts(all_update=False)
        elif c == "3":
            break
        else:
            console.print(Panel("Invalid choice.", style="red"))


def menu_download() -> None:
    while True:
        console.print(
            Panel(
                "[bold]Download Menu[/bold]\n1) From stored podcast list\n2) Enter custom RSS\n3) Return",
                style="cyan",
            )
        )
        c = console.input("Choice: ").strip()
        config, _ = init_config()
        if c == "1":
            pods = parse_podcast_list(config)
            if not pods:
                console.print(Panel("No stored podcasts.", style="yellow"))
                continue
            table = Table(title="Podcasts (NAME_ID)")
            table.add_column("NAME_ID", style="cyan")
            for _, nm, _ in pods:
                table.add_row(nm)
            console.print(table)
            inp = console.input("Which NAME_ID?: ").strip()
            match = [(l, n, d) for (l, n, d) in pods if n.lower() == inp.lower()]
            if not match:
                console.print(Panel(f"No match for '{inp}'", style="red"))
                continue
            link, showname, outd = match[0]
            oldest = (
                console.input("Download oldest first? (y/n): ").strip().lower() == "y"
            )
            cstr = console.input("How many episodes? (blank=all): ").strip()
            try:
                limit = int(cstr) if cstr else None
            except ValueError:
                limit = None
            srch = console.input("Title search term? (blank=none): ").strip()
            log_yn = console.input("Enable logging? (y/n): ").strip().lower() == "y"
            verb = console.input("Verbose? (y/n): ").strip().lower() == "y"
            if log_yn:
                setup_logging()
            download_podcast_rss(
                link,
                outd,
                count=limit,
                searchby=srch,
                verbose=verb,
                oldest_first=oldest,
                format_str="default",
            )
        elif c == "2":
            rss_url = console.input("Enter RSS URL: ").strip()
            if not rss_url:
                console.print(Panel("Invalid URL.", style="red"))
                continue
            fmt = (
                console.input("Filename format (default/daily): ").strip().lower()
                or "default"
            )
            oldest = console.input("Oldest first? (y/n): ").strip().lower() == "y"
            cstr = console.input("How many episodes? (blank=all): ").strip()
            try:
                limit = int(cstr) if cstr else None
            except ValueError:
                limit = None
            srch = console.input("Title search term? (blank=none): ").strip()
            def_out = config["system"].get("default_output_dir", DEFAULT_OUTPUT_DIR)
            outdir = (
                console.input(f"Output dir [default: {def_out}]: ").strip() or def_out
            )
            ensure_output_dir(outdir)
            log_yn = console.input("Enable logging? (y/n): ").strip().lower() == "y"
            verb = console.input("Verbose? (y/n): ").strip().lower() == "y"
            if log_yn:
                setup_logging()
            download_podcast_rss(
                rss_url,
                outdir,
                count=limit,
                searchby=srch,
                verbose=verb,
                oldest_first=oldest,
                format_str=fmt,
            )
        elif c == "3":
            break
        else:
            console.print(Panel("Invalid choice.", style="red"))


###############################################################################
#                                  MAIN                                       #
###############################################################################


def main() -> None:
    config, _ = init_config()
    set_window_size(config)
    console.print(Panel(f"=== prx {VERSION} ===", style="bold magenta"))
    while True:
        menu = (
            "[bold]Main Menu[/bold]\n"
            "1) Download Podcasts\n"
            "2) Update Podcasts\n"
            "3) Settings\n"
            "4) About\n"
            "5) Exit"
        )
        console.print(Panel(menu, title="prx", style="magenta"))
        c = console.input("Choice: ").strip()
        if c == "1":
            menu_download()
        elif c == "2":
            menu_update()
        elif c == "3":
            menu_settings()
        elif c == "4":
            menu_about()
        elif c == "5":
            console.print(Panel("Exiting...", style="bold magenta"))
            break
        else:
            console.print(Panel("Invalid choice.", style="red"))
    console.print(Panel("=== Thanks for using prx ===", style="bold magenta"))


if __name__ == "__main__":
    main()
