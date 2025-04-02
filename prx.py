#!/usr/bin/env python3
import configparser
import curses
import logging
import os
import re
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import feedparser
import httpx
import questionary
import requests
from rich import print as rprint
from rich.panel import Panel
from rich.progress import BarColumn, Progress, ProgressColumn, TextColumn, TimeElapsedColumn

# Global base directory (can be overridden by env var or CLI arg)
BASE_DIR = os.environ.get("PRX_BASE_DIR", r"H:\tools")
CONFIG_PATH = os.path.join(BASE_DIR, "prx.ini")
DEFAULT_OUTPUT_DIR = os.path.join(BASE_DIR, "downloads")
DEFAULT_LOG_DIR = os.path.join(BASE_DIR, "logs")

# Default settings
DEFAULT_TIMEOUT = 10
DEFAULT_MAX_RETRIES = 3
DEFAULT_INITIAL_BACKOFF = 2
DEFAULT_HTTPS_ONLY = False
DEFAULT_TOLERANCE_MB = 5
DEFAULT_WINDOW_WIDTH = 120
DEFAULT_WINDOW_HEIGHT = 30

VERSION = "2.2.0 [Optimized & Updated UI]"

FAILED_DOWNLOADS: List[Dict[str, str]] = []


###############################################################################
#                             Utility Classes                                 #
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
#                          Curses Window Resizing                             #
###############################################################################

def set_window_size_curses(width: int, height: int) -> None:
    """
    Adjust the console window size on Windows using curses.
    Note: curses must be available and may require windows-curses on Windows.
    """
    try:
        if os.name != "nt":
            return
        # Initialize curses
        stdscr = curses.initscr()
        curses.resize_term(height, width)
        curses.endwin()
    except Exception as e:
        rprint(Panel(f"Failed to set window size: {e}", style="red"))


###############################################################################
#                              Helper Functions                               #
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

def ensure_output_dir(output_dir: str) -> None:
    """Ensure the output directory exists; create if not."""
    try:
        os.makedirs(output_dir, exist_ok=True)
    except OSError as e:
        rprint(Panel(f"Could not create '{output_dir}': {e}", style="red"))
        sys.exit(1)


def init_config() -> Tuple[configparser.ConfigParser, str]:
    """
    Load or create a default prx.ini.
    """
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    config = configparser.ConfigParser()
    if os.path.exists(CONFIG_PATH):
        config.read(CONFIG_PATH)
        rprint(Panel(f"Loaded config from:\n{CONFIG_PATH}", title="Config", style="blue"))
    else:
        rprint(Panel(f"No config found. Creating default at:\n{CONFIG_PATH}", title="Config", style="yellow"))
        config["user"] = {"name": "", "password": ""}
        config["system"] = {
            "os": "windows",
            "default_output_dir": DEFAULT_OUTPUT_DIR,
            "download_timeout": str(DEFAULT_TIMEOUT),
            "max_retries": str(DEFAULT_MAX_RETRIES),
            "initial_retry_backoff": str(DEFAULT_INITIAL_BACKOFF),
            "https_only": str(DEFAULT_HTTPS_ONLY),
            "tolerance_mb": str(DEFAULT_TOLERANCE_MB),
            "window_width": str(DEFAULT_WINDOW_WIDTH),
            "window_height": str(DEFAULT_WINDOW_HEIGHT),
        }
        config["logging"] = {
            "log_dir": DEFAULT_LOG_DIR,
            "log_level": "INFO",
        }
        config["Podcasts"] = {"podcast_list": ""}
        with open(CONFIG_PATH, "w") as cf:
            config.write(cf)
        rprint(Panel("Default prx.ini created.", title="Config", style="green"))
    return config, CONFIG_PATH


def setup_logging() -> None:
    """Set up logging based on config."""
    config, _ = init_config()
    log_dir = config["logging"].get("log_dir", DEFAULT_LOG_DIR)
    level = config["logging"].get("log_level", "INFO")
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    try:
        os.makedirs(log_dir, exist_ok=True)
    except OSError as e:
        rprint(Panel(f"Cannot create log dir '{log_dir}': {e}", style="red"))
        log_dir = ""
    tstamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"session_{tstamp}.log") if log_dir else None
    logging.basicConfig(
        filename=log_file if log_file else None,
        filemode="w",
        format="%(asctime)s - %(levelname)s - %(message)s",
        level=numeric_level,
    )
    if log_file:
        rprint(Panel(f"Logging to:\n{log_file}", title="Logging", style="green"))
    else:
        rprint(Panel("Logging to console only.", title="Logging", style="yellow"))
    logging.info("Logging initialized.")


def validate_config() -> None:
    """Ensure the config has the required user info."""
    config, _ = init_config()
    changed = False
    if not config["user"].get("name"):
        name = questionary.text("Enter your name:").ask()
        config["user"]["name"] = name or ""
        changed = True
    if not config["user"].get("password"):
        password = questionary.password("Enter your password:").ask()
        config["user"]["password"] = password or ""
        changed = True
    if changed:
        with open(CONFIG_PATH, "w") as cf:
            config.write(cf)
        rprint(Panel("Config updated!", style="green"))
    else:
        rprint(Panel("Config is fine.", style="green"))


###############################################################################
#                     Podcast List Management Functions                       #
###############################################################################

def parse_podcast_list(config: configparser.ConfigParser) -> List[Tuple[str, str, str]]:
    """Parse the podcast_list from [Podcasts] section."""
    line = config["Podcasts"].get("podcast_list", "").strip()
    if not line:
        return []
    results = []
    for entry in [x.strip() for x in line.split(";") if x.strip()]:
        parts = [p.strip() for p in entry.split(" : ")]
        if len(parts) == 3:
            results.append((parts[0], parts[1], parts[2]))
    return results


def manage_podcasts_in_config() -> None:
    """
    Manage the [Podcasts] section in the config.
    Format: PODCAST_LINK : NAME_ID : OUTPUT_DIRECTORY (semicolon-separated).
    """
    config, _ = init_config()
    while True:
        choice = questionary.select(
            "Manage Podcasts:",
            choices=[
                "View list",
                "Add a new one",
                "Edit existing",
                "Remove",
                "Return",
            ],
        ).ask()
        entries = parse_podcast_list(config)
        if choice == "View list":
            if not entries:
                rprint(Panel("No podcasts.", style="yellow"))
            else:
                table_str = "\n".join(f"{n} -> {l} | {o}" for l, n, o in entries)
                rprint(Panel(table_str, title="Podcast List", style="cyan"))
        elif choice == "Add a new one":
            new_p = questionary.text("Enter LINK : NAME_ID : OUTPUT_DIR:").ask().strip()
            parts = [x.strip() for x in new_p.split(" : ")]
            if len(parts) == 3:
                entries.append((parts[0], parts[1], parts[2]))
                new_str = " ; ".join(f"{l} : {n} : {o}" for (l, n, o) in entries)
                config["Podcasts"]["podcast_list"] = new_str
                with open(CONFIG_PATH, "w") as cf:
                    config.write(cf)
                rprint(Panel(f"Added '{parts[1]}'", style="green"))
            else:
                rprint(Panel("Invalid format.", style="red"))
        elif choice == "Edit existing":
            if not entries:
                rprint(Panel("No podcasts to edit.", style="yellow"))
                continue
            names = [n for (_, n, _) in entries]
            selected = questionary.select("Select podcast to edit:", choices=names).ask()
            for i, (l, n, o) in enumerate(entries):
                if n.lower() == selected.lower():
                    new_val = questionary.text("New LINK : NAME_ID : OUT_DIR (blank=skip):").ask().strip()
                    if new_val:
                        parts = [p.strip() for p in new_val.split(" : ")]
                        if len(parts) == 3:
                            entries[i] = (parts[0], parts[1], parts[2])
                        else:
                            rprint(Panel("Bad format. Skipping.", style="red"))
                            continue
                    break
            final_str = " ; ".join(f"{l} : {n} : {o}" for (l, n, o) in entries)
            config["Podcasts"]["podcast_list"] = final_str
            with open(CONFIG_PATH, "w") as cf:
                config.write(cf)
            rprint(Panel("Podcast updated.", style="green"))
        elif choice == "Remove":
            if not entries:
                rprint(Panel("No podcasts to remove.", style="yellow"))
                continue
            names = [n for (_, n, _) in entries]
            selected = questionary.select("Select podcast to remove:", choices=names).ask()
            entries = [entry for entry in entries if entry[1].lower() != selected.lower()]
            final_str = " ; ".join(f"{l} : {n} : {o}" for (l, n, o) in entries)
            config["Podcasts"]["podcast_list"] = final_str
            with open(CONFIG_PATH, "w") as cf:
                config.write(cf)
            rprint(Panel(f"Removed '{selected}'", style="green"))
        elif choice == "Return":
            break


###############################################################################
#                            Download Functions                               #
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
    """
    if not os.path.exists(file_path):
        return True
    local_size = os.path.getsize(file_path)
    remote_size: Optional[int] = enclosure_length if enclosure_length and enclosure_length > 0 else None
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
    if local_size < remote_size - tolerance:
        return True
    return False


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
    Returns True on success.
    """
    if verbose:
        info = get_extended_server_info(url, timeout)
        info_str = "\n".join(f"{k}: {v}" for k, v in info.items())
        rprint(Panel(f"Server Info:\n{info_str}", style="cyan"))
    for attempt in range(1, max_retries + 1):
        start_t = time.time()
        try:
            config, _ = init_config()
            https_only = config["system"].getboolean("https_only", fallback=DEFAULT_HTTPS_ONLY)
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
                transient=True,
            ) as progress:
                task = progress.add_task(description, total=total_size)
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        progress.update(task, advance=len(chunk))
            elapsed = time.time() - start_t
            speed = total_size / elapsed if elapsed else 0
            if verbose:
                rprint(Panel(f"Downloaded in {elapsed:.2f}s at {human_readable_speed(speed)}", style="green"))
            logging.info(f"Downloaded: {url} -> {output_path}")
            return True
        except requests.Timeout:
            rprint(Panel(f"Timeout {attempt}/{max_retries}: {url}", title="Timeout", style="red"))
            logging.exception(f"Timeout {attempt} for {url}")
        except Exception as e:
            rprint(Panel(f"Error {attempt}/{max_retries} for {url}\n{e}", title="Download Error", style="red"))
            logging.exception(f"Error {attempt} for {url}")
        time.sleep(initial_backoff * (2 ** (attempt - 1)))
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
    """
    logging.info(f"Download from {rss_url}, dir={output_dir}, count={count}, search={searchby}, oldest={oldest_first}, fmt={format_str}")
    ensure_output_dir(output_dir)
    config, _ = init_config()
    try:
        tol_mb = float(config["system"].get("tolerance_mb", str(DEFAULT_TOLERANCE_MB)))
    except ValueError:
        tol_mb = DEFAULT_TOLERANCE_MB
    tolerance = int(tol_mb * 1024 * 1024)
    try:
        timeout = int(config["system"].get("download_timeout", str(DEFAULT_TIMEOUT)))
    except ValueError:
        timeout = DEFAULT_TIMEOUT

    feed = feedparser.parse(rss_url)
    if not feed.entries:
        rprint(Panel("No episodes found in feed.", style="yellow"))
        return

    entries = [e for e in feed.entries if (searchby.lower() in e.title.lower())] if searchby else feed.entries
    if not entries:
        rprint(Panel(f"No episodes match '{searchby}'.", style="yellow"))
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
    sorted_eps = ([ep for (ep, _) in with_time] + without_time) if oldest_first else (without_time + [ep for (ep, _) in with_time])
    to_download = sorted_eps[:count] if count else sorted_eps
    if not to_download:
        rprint(Panel("No episodes left after sorting/filtering.", style="yellow"))
        return

    for idx, ep in enumerate(to_download, start=1):
        title = ep.title
        if not ep.enclosures:
            rprint(Panel(f"'{title}' has no enclosure link. Skipping.", style="yellow"))
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
            if not is_file_damaged(file_path, feed_len, enclosure_url, tolerance, timeout):
                rprint(Panel(f"SKIPPING: '{file_path}' found & OK.", title="Skip", style="yellow"))
                logging.info(f"Skipping complete file: {file_path}")
                continue
            else:
                rprint(Panel(f"File '{file_path}' is incomplete. Removing & re-downloading...", style="yellow"))
                os.remove(file_path)
        if verbose:
            rprint(Panel(f"Downloading:\nTitle: {title}\nURL: {enclosure_url}\nFile: {file_path}",
                         title=f"Episode {idx}/{len(to_download)}", style="blue"))
        success = download_with_progress(
            enclosure_url,
            file_path,
            description=f"Episode {idx}/{len(to_download)}",
            verbose=verbose,
            timeout=timeout,
        )
        if success:
            rprint(Panel(f"✔ Downloaded '{title}'", style="green"))
        else:
            rprint(Panel(f"❌ Failed to download '{title}'", style="red"))
            FAILED_DOWNLOADS.append({"title": title, "url": enclosure_url, "output": file_path})
    if FAILED_DOWNLOADS:
        fail_list = "\n".join(f"- {f['title']}" for f in FAILED_DOWNLOADS)
        rprint(Panel(f"Failed downloads:\n{fail_list}", style="red"))


def update_podcasts(all_update: bool = True) -> None:
    """Update podcasts from the stored list."""
    config, _ = init_config()
    shows = parse_podcast_list(config)
    if not shows:
        rprint(Panel("No podcasts in config!", style="yellow"))
        return
    if all_update:
        rprint(Panel("Updating ALL podcasts...", style="magenta"))
        for link, name_id, out_dir in shows:
            rprint(Panel(f"Updating '{name_id}'", style="cyan"))
            download_podcast_rss(link, out_dir, count=None, verbose=True)
        rprint(Panel("All updates done.", style="green"))
    else:
        names = [n for (_, n, _) in shows]
        selected = questionary.select("Which podcast to update?", choices=names).ask()
        found = [item for item in shows if item[1].lower() == selected.lower()]
        if not found:
            rprint(Panel(f"No match for '{selected}'", style="red"))
            return
        link, showname, outd = found[0]
        rprint(Panel(f"Updating '{showname}'...", style="cyan"))
        download_podcast_rss(link, outd, count=None, verbose=True)
        rprint(Panel("Update complete.", style="green"))


###############################################################################
#                                 Menu UI                                     #
###############################################################################

def menu_settings() -> None:
    while True:
        action = questionary.select(
            "Settings",
            choices=[
                "Init (create/load prx.ini)",
                "Manage config (view/edit)",
                "Manage podcasts list",
                "Return",
            ],
        ).ask()
        if action == "Init (create/load prx.ini)":
            validate_config()
        elif action == "Manage config (view/edit)":
            config, _ = init_config()
            view_edit = questionary.select("Choose action:", choices=["View", "Edit", "Return"]).ask()
            if view_edit == "View":
                with open(CONFIG_PATH, "r") as cfile:
                    data = cfile.read()
                rprint(Panel(data, title="prx.ini", style="blue"))
            elif view_edit == "Edit":
                validate_config()
                adv = questionary.confirm("Edit advanced settings?").ask()
                if adv:
                    changed = False
                    current_out = config["system"].get("default_output_dir", DEFAULT_OUTPUT_DIR)
                    new_out = questionary.text(f"Current output dir: {current_out}\nNew? (blank to skip):").ask()
                    if new_out:
                        config["system"]["default_output_dir"] = new_out
                        changed = True

                    current_log = config["logging"].get("log_dir", DEFAULT_LOG_DIR)
                    new_log = questionary.text(f"Current log dir: {current_log}\nNew? (blank to skip):").ask()
                    if new_log:
                        config["logging"]["log_dir"] = new_log
                        changed = True

                    current_lvl = config["logging"].get("log_level", "INFO")
                    new_lvl = questionary.text(
                        f"Current log level: {current_lvl}\nNew (DEBUG/INFO/WARNING/ERROR/CRITICAL, blank to skip):"
                    ).ask()
                    if new_lvl and new_lvl.upper() in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
                        config["logging"]["log_level"] = new_lvl.upper()
                        changed = True

                    current_tol = config["system"].get("tolerance_mb", str(DEFAULT_TOLERANCE_MB))
                    new_tol = questionary.text(f"Current tolerance (MB): {current_tol}\nNew? (blank to skip):").ask()
                    if new_tol:
                        config["system"]["tolerance_mb"] = new_tol
                        changed = True

                    current_width = config["system"].get("window_width", str(DEFAULT_WINDOW_WIDTH))
                    new_width = questionary.text(f"Current window width: {current_width}\nNew? (blank to skip):").ask()
                    if new_width:
                        config["system"]["window_width"] = new_width
                        changed = True

                    current_height = config["system"].get("window_height", str(DEFAULT_WINDOW_HEIGHT))
                    new_height = questionary.text(f"Current window height: {current_height}\nNew? (blank to skip):").ask()
                    if new_height:
                        config["system"]["window_height"] = new_height
                        changed = True

                    if changed:
                        with open(CONFIG_PATH, "w") as cf:
                            config.write(cf)
                        rprint(Panel("Config updated.", style="green"))
                    else:
                        rprint(Panel("No changes made.", style="green"))
            elif view_edit == "Return":
                continue
        elif action == "Manage podcasts list":
            manage_podcasts_in_config()
        elif action == "Return":
            break


def menu_download() -> None:
    config, _ = init_config()
    choice = questionary.select(
        "Download Menu",
        choices=[
            "From stored podcast list",
            "Enter custom RSS",
            "Return",
        ],
    ).ask()
    if choice == "From stored podcast list":
        podcasts = parse_podcast_list(config)
        if not podcasts:
            rprint(Panel("No stored podcasts.", style="yellow"))
            return
        names = [n for (_, n, _) in podcasts]
        selected = questionary.select("Which NAME_ID?", choices=names).ask()
        match = [item for item in podcasts if item[1].lower() == selected.lower()]
        if not match:
            rprint(Panel(f"No match for '{selected}'", style="red"))
            return
        link, showname, outd = match[0]
        oldest = questionary.confirm("Download oldest first?").ask()
        limit_str = questionary.text("How many episodes? (blank=all)").ask()
        try:
            limit = int(limit_str) if limit_str.strip() else None
        except ValueError:
            limit = None
        srch = questionary.text("Title search term? (blank for none)").ask()
        log_yn = questionary.confirm("Enable logging?").ask()
        verb = questionary.confirm("Verbose?").ask()
        if log_yn:
            setup_logging()
        download_podcast_rss(link, outd, count=limit, searchby=srch, verbose=verb, oldest_first=oldest, format_str="default")
    elif choice == "Enter custom RSS":
        rss_url = questionary.text("Enter RSS URL:").ask().strip()
        if not rss_url:
            rprint(Panel("Invalid URL.", style="red"))
            return
        fmt = questionary.text("Filename format (default/daily):", default="default").ask().lower()
        oldest = questionary.confirm("Download oldest first?").ask()
        limit_str = questionary.text("How many episodes? (blank=all)").ask()
        try:
            limit = int(limit_str) if limit_str.strip() else None
        except ValueError:
            limit = None
        srch = questionary.text("Title search term? (blank for none)").ask()
        def_out = config["system"].get("default_output_dir", DEFAULT_OUTPUT_DIR)
        outdir = questionary.text(f"Output dir [default: {def_out}]:", default=def_out).ask()
        ensure_output_dir(outdir)
        log_yn = questionary.confirm("Enable logging?").ask()
        verb = questionary.confirm("Verbose?").ask()
        if log_yn:
            setup_logging()
        download_podcast_rss(rss_url, outdir, count=limit, searchby=srch, verbose=verb, oldest_first=oldest, format_str=fmt)
    # "Return" does nothing


def menu_update() -> None:
    choice = questionary.select(
        "Update Podcasts",
        choices=[
            "Update All",
            "Update One",
            "Return",
        ],
    ).ask()
    if choice == "Update All":
        update_podcasts(all_update=True)
    elif choice == "Update One":
        update_podcasts(all_update=False)
    # "Return" does nothing


def menu_about() -> None:
    choice = questionary.select(
        "About",
        choices=[
            f"About (version {VERSION})",
            "Return",
        ],
    ).ask()
    if choice.startswith("About"):
        rprint(Panel(
            f"prx {VERSION}\nAll settings adjustable via the config file.\nWindow size and tolerance (in MB) are configurable.",
            style="green",
        ))


###############################################################################
#                                  MAIN                                       #
###############################################################################

def main() -> None:
    config, _ = init_config()
    # Optionally set window size using curses (Windows only)
    try:
        width = int(config["system"].get("window_width", str(DEFAULT_WINDOW_WIDTH)))
        height = int(config["system"].get("window_height", str(DEFAULT_WINDOW_HEIGHT)))
        set_window_size_curses(width, height)
    except Exception:
        pass

    rprint(Panel(f"=== prx {VERSION} ===", style="bold magenta"))
    while True:
        choice = questionary.select(
            "Main Menu",
            choices=[
                "Download Podcasts",
                "Update Podcasts",
                "Settings",
                "About",
                "Exit",
            ],
        ).ask()
        if choice == "Download Podcasts":
            menu_download()
        elif choice == "Update Podcasts":
            menu_update()
        elif choice == "Settings":
            menu_settings()
        elif choice == "About":
            menu_about()
        elif choice == "Exit":
            rprint(Panel("Exiting...", style="bold magenta"))
            break
    pcip_banner = r"""
    ██████╗ ██████╗ ██╗██████╗ 
    ██╔══██╗██╔═══╝ ██║██╔══██╗
    ██████╔╝██║     ██║██████╔╝
    ██╔═══╝ ██║     ██║██╔═══╝ 
    ██║     ╚██████╗██║██║     
    ╚═╝      ╚═════╝╚═╝╚═╝     
    """
    rprint(Panel(pcip_banner, title="DRIP", subtitle="Discreet RSS Intelligence Parser", style="bold cyan"))


if __name__ == "__main__":
    main()
