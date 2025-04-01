#!/usr/bin/env python3
import os
import sys
import time
import configparser
import logging
import requests
import httpx
import feedparser
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import questionary
from questionary import Style
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import (
    Progress,
    BarColumn,
    TextColumn,
    TimeElapsedColumn,
    ProgressColumn
)

###############################################################################
#                       GLOBAL SETTINGS AND CONSTANTS                         #
###############################################################################

console = Console()
QUIET_MODE: bool = False

VERSION = "2.3.1 [TDZ Edition]"
FAILED_DOWNLOADS: List[Dict[str, str]] = []

# Default fallback values
DEFAULT_TIMEOUT = 10
DEFAULT_MAX_RETRIES = 3
DEFAULT_INITIAL_BACKOFF = 2
DEFAULT_HTTPS_ONLY = False
DEFAULT_TOLERANCE_MB = 10
DEFAULT_WINDOW_WIDTH = 100
DEFAULT_WINDOW_HEIGHT = 40
DEFAULT_OUTPUT_DIR = r"G:\TDZ"
DEFAULT_LOG_DIR = r"G:\tools\logs"


###############################################################################
#                         CUSTOM STYLE FOR QUESTIONARY                        #
###############################################################################

# I'm using a style so the text-based prompts look cooler
custom_style = Style([
    ("qmark",       "fg:#673ab7 bold"),
    ("question",    "fg:#00BCD4 bold"),
    ("answer",      "fg:#F44336 bold"),
    ("pointer",     "fg:#673ab7 bold"),
    ("highlighted", "fg:#673ab7 bold"),
    ("selected",    "fg:#cc5454"),
    ("separator",   "fg:#cc5454"),
    ("instruction", "fg:#ffc107"),
    ("text",        ""),
    ("disabled",    "fg:#858585 italic")
])


###############################################################################
#                 LOAD/CREATE CONFIG + SETUP THINGS WE NEED                   #
###############################################################################

def get_config_path() -> str:
    # This is where we keep our config file
    return r"G:\tools\tdz-prx.ini"


def init_config() -> Tuple[configparser.ConfigParser, str]:
    """
    Check if we already have tdz-prx.ini in G:\tools\.
    If not, let's create a basic one so we can start with some defaults.
    """
    config_path = get_config_path()
    os.makedirs(os.path.dirname(config_path), exist_ok=True)

    config = configparser.ConfigParser()

    if os.path.exists(config_path):
        config.read(config_path)
    else:
        # Let's create a new config
        config["user"] = {"name": "", "password": ""}
        config["system"] = {
            "os": "windows",
            "default_output_dir": DEFAULT_OUTPUT_DIR,
            "download_timeout": str(DEFAULT_TIMEOUT),
            "max_retries": str(DEFAULT_MAX_RETRIES),
            "initial_retry_backoff": str(DEFAULT_INITIAL_BACKOFF),
            "https_only": str(DEFAULT_HTTPS_ONLY),
            "quiet_mode": str(QUIET_MODE),
            "tolerance_mb": str(DEFAULT_TOLERANCE_MB),
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
        console.print(
            Panel(f"Created a default prx.ini at {config_path}", style="yellow")
        )

    return config, config_path


def ensure_output_dir(output_dir: str) -> None:
    """Make sure the directory we're saving files to exists, or else throw an error."""
    try:
        os.makedirs(output_dir, exist_ok=True)
    except OSError as e:
        console.print(Panel(f"Couldn't create '{output_dir}': {e}", style="red"))
        sys.exit(1)


def setup_logging() -> None:
    """
    If user wants logs, configure them. Otherwise, just console logs.
    """
    config, _ = init_config()
    log_dir = config["logging"].get("log_dir", DEFAULT_LOG_DIR)
    level = config["logging"].get("log_level", "INFO")
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    try:
        os.makedirs(log_dir, exist_ok=True)
    except OSError:
        console.print(
            Panel(
                f"Couldn't make log dir '{log_dir}', log to console only",
                style="red"
            )
        )
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
        console.print(Panel(f"Logging to: {log_file}", title="Logging", style="green"))
    else:
        console.print(Panel("Logging to console only", title="Logging", style="green"))
    logging.info("Logging set up successfully.")


###############################################################################
#                           HELPER FOR DAMAGED FILES                          #
###############################################################################

def is_file_damaged(
    file_path: str,
    enclosure_length: Optional[int],
    mp3_url: Optional[str],
    tolerance: int,
    timeout: int,
    do_head_if_needed: bool = True,
) -> bool:

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
        # If we can't get a remote size, let's assume it's all good
        return False

    if local_size < (remote_size - tolerance):
        return True

    return False


###############################################################################
#                           DOWNLOAD & PROGRESS LOGIC                         #
###############################################################################

def human_readable_speed(bps: float) -> str:
    """Helper so we can print speeds in B/s, KB/s, or MB/s."""
    if bps < 1024:
        return f"{bps:.2f} B/s"
    elif bps < 1024 * 1024:
        return f"{bps/1024:.2f} KB/s"
    else:
        return f"{bps/(1024*1024):.2f} MB/s"


class MBPercentColumn(ProgressColumn):
    """
    Custom Rich progress column that shows how many MB we've downloaded
    and what percentage is done.
    """
    def render(self, task) -> str:
        if task.total is None or task.total == 0:
            return "0.00MB/??MB (0%)"
        downloaded_mb = task.completed / (1024 * 1024)
        total_mb = task.total / (1024 * 1024)
        pct = (task.completed / task.total) * 100
        return f"{downloaded_mb:5.2f}MB/{total_mb:5.2f}MB ({pct:5.1f}%)"


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
    Actually download the file while showing a progress bar. If it times out
    or fails, we retry with exponential backoff.
    """
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
                console=console,
                transient=QUIET_MODE,
            ) as progress:
                task_id = progress.add_task(description, total=total_size)
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        progress.update(task_id, advance=len(chunk))

            elapsed = time.time() - start_t
            speed = total_size / elapsed if elapsed else 0
            if verbose:
                console.print(
                    Panel(
                        f"Downloaded in {elapsed:.2f}s at {human_readable_speed(speed)}",
                        style="green",
                    )
                )
            logging.info(f"Downloaded from {url} to {output_path}")
            return True

        except requests.Timeout:
            console.print(Panel(
                f"Timeout {attempt}/{max_retries} => {url}",
                title="Timeout",
                style="red"
            ))
            logging.exception(f"Timeout {attempt} for {url}")

        except Exception as e:
            console.print(Panel(
                f"Error {attempt}/{max_retries} for {url}\n{e}",
                title="Download Error",
                style="red"
            ))
            logging.exception(f"Error {attempt} for {url}")

        # Use exponential backoff
        backoff = initial_backoff * (2 ** (attempt - 1))
        time.sleep(backoff)

    return False


###############################################################################
#                   DATE CODE PARSING & FILENAME CREATION                     #
###############################################################################

def parse_six_digit_date(code: str) -> Optional[str]:
    """
    Some titles have 6-digit codes that represent a date: YYMMDD. Let's try
    to parse them and produce YYYY-MM-DD so it's easily sortable.
    I'll assume that if YY >= 50, it's 19xx; else it's 20xx.
    """
    if not re.match(r"^\d{6}$", code):
        return None

    yy = int(code[0:2])
    mm = int(code[2:4])
    dd = int(code[4:6])

    century = 1900 if yy >= 50 else 2000
    year = century + yy

    try:
        dt = datetime(year, mm, dd)
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return None


def build_episode_filename(original_title: str, fmt: str) -> str:
    """
    We might see a 6-digit date in some titles. If it's found, we'll format it
    as 'YYYY-MM-DD Title.mp3'. If 'fmt' is 'daily', we specifically check if
    the title ends in a 6-digit code and put that code up front in the final name.
    Otherwise, we just sanitize everything.
    """
    def sanitize(txt: str) -> str:
        return "".join(c for c in txt if c.isalnum() or c in " _-").rstrip()

    if fmt == "daily":
        pattern = r"^(.*)\s+(\d{6})$"
        m = re.match(pattern, original_title)
        if m:
            main_part, date_part = m.groups()
            iso_date = parse_six_digit_date(date_part)
            if iso_date:
                # "2023-06-24 My Title"
                return f"{iso_date} {sanitize(main_part)}".strip()
            else:
                # We couldn't parse that code, so let's just do the code + sanitized text
                return f"{date_part} {sanitize(main_part)}".strip()
        else:
            code_match = re.search(r"\b(\d{6})\b", original_title)
            if code_match:
                found_code = code_match.group(1)
                iso_date = parse_six_digit_date(found_code)
                if iso_date:
                    rest = sanitize(original_title.replace(found_code, "")).strip()
                    return f"{iso_date} {rest}".strip()
            return sanitize(original_title)
    else:
        code_match = re.search(r"\b(\d{6})\b", original_title)
        if code_match:
            found_code = code_match.group(1)
            iso_date = parse_six_digit_date(found_code)
            if iso_date:
                rest = sanitize(original_title.replace(found_code, "")).strip()
                return f"{iso_date} {rest}".strip()
        return sanitize(original_title)


###############################################################################
#                         DOWNLOAD PODCAST FEED ENTRIES                       #
###############################################################################

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
    Fetch feed entries, then download them one by one if they aren't already
    complete or are damaged. We'll skip any that are good.
    """
    logging.info(f"Podcast fetch from {rss_url} -> {output_dir}")

    ensure_output_dir(output_dir)
    config, _ = init_config()

    # Figure out how many bytes of tolerance we want
    try:
        tol_mb = float(config["system"].get("tolerance_mb", str(DEFAULT_TOLERANCE_MB)))
    except ValueError:
        tol_mb = DEFAULT_TOLERANCE_MB
    tolerance = int(tol_mb * 1024 * 1024)

    # Timeout from config
    try:
        timeout = int(config["system"].get("download_timeout", str(DEFAULT_TIMEOUT)))
    except ValueError:
        timeout = DEFAULT_TIMEOUT

    feed = feedparser.parse(rss_url)
    if not feed.entries:
        console.print(Panel("No entries found in feed.", style="yellow"))
        return

    if searchby:
        entries = [e for e in feed.entries if searchby.lower() in e.title.lower()]
    else:
        entries = feed.entries

    if not entries:
        console.print(Panel(f"No episodes match '{searchby}'.", style="yellow"))
        return

    def get_date(e: Any) -> Optional[float]:
        if hasattr(e, "published_parsed") and e.published_parsed:
            return time.mktime(e.published_parsed)
        if hasattr(e, "updated_parsed") and e.updated_parsed:
            return time.mktime(e.updated_parsed)
        return None

    with_time, without_time = [], []
    for ep in entries:
        dt = get_date(ep)
        if dt is not None:
            with_time.append((ep, dt))
        else:
            without_time.append(ep)

    # Sort episodes either oldest first or newest first
    with_time.sort(key=lambda x: x[1], reverse=(not oldest_first))
    if oldest_first:
        sorted_eps = [ep for (ep, _) in with_time] + without_time
    else:
        sorted_eps = without_time + [ep for (ep, _) in reversed(with_time)]

    to_download = sorted_eps[:count] if count else sorted_eps
    if not to_download:
        console.print(Panel("No episodes left to download after sorting/filtering.", style="yellow"))
        return

    for idx, ep in enumerate(to_download, start=1):
        title = ep.title
        if not ep.enclosures:
            console.print(Panel(
                f"'{title}' has no enclosure link. Skipping.",
                style="yellow"
            ))
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
                    Panel(f"SKIPPING: '{file_path}' already looks complete.", style="yellow")
                )
                logging.info(f"Skipping fully downloaded file: {file_path}")
                continue
            else:
                console.print(
                    Panel(f"Removing incomplete file: {file_path}", style="yellow")
                )
                os.remove(file_path)

        if verbose:
            console.print(
                Panel(
                    f"[bold]Downloading[/bold]\nTitle: {title}\nURL: {enclosure_url}",
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
            console.print(Panel(f"[green]✔ Downloaded[/green] '{title}'", style="green"))
        else:
            console.print(Panel(f"[red]❌ Failed to download[/red] '{title}'", style="red"))
            FAILED_DOWNLOADS.append(
                {"title": title, "url": enclosure_url, "output": file_path}
            )

    if FAILED_DOWNLOADS:
        fail_list = "\n".join(f"- {f['title']}" for f in FAILED_DOWNLOADS)
        console.print(Panel(f"The following downloads failed:\n{fail_list}", style="red"))


###############################################################################
#                        PODCAST CONFIG & LOCAL BROWSER                       #
###############################################################################

def parse_podcast_list(config: configparser.ConfigParser) -> List[Tuple[str, str, str]]:
    """
    We'll parse the 'podcast_list' line from prx.ini
    Format: LINK : NAME_ID : OUTPUT_DIR, separated by semicolons.
    """
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


def manage_podcasts_in_config() -> None:
    """
    Let us list, add, edit, or remove podcasts from the config file, but in a more
    interactive style. We'll do everything with questionary so we don't have to type indexes.
    """
    config, config_path = init_config()
    while True:
        choice = questionary.select(
            "Manage Podcasts:",
            choices=[
                "View list",
                "Add new",
                "Edit existing",
                "Remove",
                "Return"
            ],
            style=custom_style
        ).ask()

        p_line = config["Podcasts"].get("podcast_list", "").strip()
        entries = [ch.strip() for ch in p_line.split(";") if ch.strip()]
        triplets: List[Tuple[str, str, str]] = []
        for e in entries:
            parts = [p.strip() for p in e.split(" : ")]
            if len(parts) == 3:
                triplets.append((parts[0], parts[1], parts[2]))

        if choice == "View list":
            if not triplets:
                console.print(Panel("No podcasts currently stored.", style="yellow"))
            else:
                t = Table(title="Podcast List")
                t.add_column("NAME_ID", style="cyan")
                t.add_column("Link", style="magenta")
                t.add_column("Output Dir", style="green")
                for link, n_id, outd in triplets:
                    t.add_row(n_id, link, outd)
                console.print(t)

        elif choice == "Add new":
            new_val = questionary.text(
                "Enter: LINK : NAME_ID : OUTPUT_DIR",
                style=custom_style
            ).ask()
            if not new_val:
                continue
            p_parts = [x.strip() for x in new_val.split(" : ")]
            if len(p_parts) == 3:
                triplets.append((p_parts[0], p_parts[1], p_parts[2]))
                new_str = " ; ".join(f"{l} : {n} : {o}" for (l, n, o) in triplets)
                config["Podcasts"]["podcast_list"] = new_str
                with open(config_path, "w") as cf:
                    config.write(cf)
                console.print(Panel(f"Added '{p_parts[1]}'", style="green"))
            else:
                console.print(Panel("Use: LINK : NAME_ID : OUTPUT_DIR", style="red"))

        elif choice == "Edit existing":
            if not triplets:
                console.print(Panel("No podcasts to edit right now.", style="yellow"))
                continue
            name_map = {f"{i+1}) {t[1]}": i for i, t in enumerate(triplets)}
            selection = questionary.select(
                "Which one do you want to edit?",
                choices=list(name_map.keys()),
                style=custom_style
            ).ask()
            if not selection:
                continue
            idx = name_map[selection]
            old_l, old_n, old_o = triplets[idx]

            new_val = questionary.text(
                "New LINK : NAME_ID : OUTPUT_DIR (leave blank to skip):",
                style=custom_style
            ).ask()
            if new_val:
                p2 = [p.strip() for p in new_val.split(" : ")]
                if len(p2) == 3:
                    triplets[idx] = (p2[0], p2[1], p2[2])
                else:
                    console.print(Panel("Wrong format. Skipping changes.", style="red"))

            new_str = " ; ".join(f"{l} : {n} : {o}" for (l, n, o) in triplets)
            config["Podcasts"]["podcast_list"] = new_str
            with open(config_path, "w") as cf:
                config.write(cf)
            console.print(Panel("Podcast updated!", style="green"))

        elif choice == "Remove":
            if not triplets:
                console.print(Panel("No podcasts to remove right now.", style="yellow"))
                continue
            name_map = {f"{i+1}) {t[1]}": i for i, t in enumerate(triplets)}
            selection = questionary.select(
                "Which one do you want to remove?",
                choices=list(name_map.keys()),
                style=custom_style
            ).ask()
            if not selection:
                continue
            idx = name_map[selection]
            removed = triplets.pop(idx)
            final_str = " ; ".join(f"{l} : {n} : {o}" for (l, n, o) in triplets)
            config["Podcasts"]["podcast_list"] = final_str
            with open(config_path, "w") as cf:
                config.write(cf)
            console.print(Panel(f"Removed '{removed[1]}' from the list.", style="green"))

        else:
            break


def browse_local_files() -> None:
    """
    Let me just see what mp3s are already in the local folder for each stored podcast.
    I'll let the user pick which show, then list any .mp3 files sorted by filename,
    along with a date prefix if we see one.
    """
    config, _ = init_config()
    shows = parse_podcast_list(config)
    if not shows:
        console.print(Panel("No podcasts defined yet.", style="yellow"))
        return

    # Let user pick which one to browse
    choices = [f"{i+1}) {show[1]}" for i, show in enumerate(shows)]
    sel = questionary.select(
        "Pick a podcast to see its local mp3s:",
        choices=choices,
        style=custom_style
    ).ask()
    if not sel:
        return
    idx = int(sel.split(")")[0]) - 1
    link, name_id, out_dir = shows[idx]

    if not os.path.exists(out_dir):
        console.print(Panel(f"'{out_dir}' doesn't exist, can't browse it.", style="red"))
        return

    all_files = os.listdir(out_dir)
    mp3_files = [f for f in all_files if f.lower().endswith(".mp3")]
    if not mp3_files:
        console.print(Panel("No mp3 files found in that folder.", style="yellow"))
        return

    mp3_files.sort()

    table = Table(title=f"Local MP3s for {name_id}")
    table.add_column("Filename", style="cyan")
    table.add_column("Parsed Date?", style="green")
    table.add_column("Filesize (MB)", justify="right", style="magenta")

    for fname in mp3_files:
        fpath = os.path.join(out_dir, fname)
        size_mb = os.path.getsize(fpath) / (1024 * 1024)
        date_match = re.match(r"^(\d{4}-\d{2}-\d{2})", fname)
        parsed_date_str = date_match.group(1) if date_match else ""
        table.add_row(fname, parsed_date_str, f"{size_mb:0.2f}")

    console.print(table)


###############################################################################
#                                MENU & MAIN                                  #
###############################################################################

def handle_init_command() -> None:
    """Initialize config if needed, and ask user for name & password if not set."""
    console.print(Panel("Initializing config file...", style="blue"))
    config, _ = init_config()
    if not config["user"].get("name"):
        name = questionary.text("Enter your name:", style=custom_style).ask()
        config["user"]["name"] = name or ""
    if not config["user"].get("password"):
        pwd = questionary.password("Enter your password:", style=custom_style).ask()
        config["user"]["password"] = pwd or ""

    with open(get_config_path(), "w") as cf:
        config.write(cf)
    console.print(Panel("Config is good to go now!", style="green"))


def manage_settings_config() -> None:
    """We can view the ini, or change user/password, or tweak advanced settings here."""
    config, config_path = init_config()
    action = questionary.select(
        "What would you like to do in Settings?",
        choices=["View tdz-prx.ini", "Edit user/password", "Edit advanced", "Return"],
        style=custom_style
    ).ask()

    if action == "View tdz-prx.ini":
        if os.path.exists(config_path):
            with open(config_path, "r") as cfile:
                cdata = cfile.read()
            console.print(Panel(cdata, title="tdz-prx.ini", style="blue"))
        else:
            console.print(Panel("Couldn't find the config file.", style="red"))

    elif action == "Edit user/password":
        name = questionary.text(
            "User name:",
            default=config["user"].get("name", ""),
            style=custom_style
        ).ask()
        pwd = questionary.password("Password:", style=custom_style).ask()
        config["user"]["name"] = name
        config["user"]["password"] = pwd
        with open(config_path, "w") as cf:
            config.write(cf)
        console.print(Panel("User info updated.", style="green"))

    elif action == "Edit advanced":
        def_out = config["system"].get("default_output_dir", DEFAULT_OUTPUT_DIR)
        new_out = questionary.text(
            "Default download folder:",
            default=def_out,
            style=custom_style
        ).ask()
        config["system"]["default_output_dir"] = new_out

        def_logdir = config["logging"].get("log_dir", DEFAULT_LOG_DIR)
        new_logdir = questionary.text(
            "Log folder:",
            default=def_logdir,
            style=custom_style
        ).ask()
        config["logging"]["log_dir"] = new_logdir

        def_loglevel = config["logging"].get("log_level", "INFO")
        new_loglevel = questionary.select(
            "Log level?",
            choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
            default=def_loglevel,
            style=custom_style
        ).ask()
        config["logging"]["log_level"] = new_loglevel

        tolerance_mb = config["system"].get("tolerance_mb", str(DEFAULT_TOLERANCE_MB))
        new_tol = questionary.text(
            "How many MB of tolerance for partial downloads?",
            default=tolerance_mb,
            style=custom_style
        ).ask()
        config["system"]["tolerance_mb"] = new_tol

        width = config["system"].get("window_width", str(DEFAULT_WINDOW_WIDTH))
        new_width = questionary.text(
            "Console window width:",
            default=width,
            style=custom_style
        ).ask()
        config["system"]["window_width"] = new_width

        height = config["system"].get("window_height", str(DEFAULT_WINDOW_HEIGHT))
        new_height = questionary.text(
            "Console window height:",
            default=height,
            style=custom_style
        ).ask()
        config["system"]["window_height"] = new_height

        with open(config_path, "w") as cf:
            config.write(cf)
        console.print(Panel("Advanced settings updated.", style="green"))

    else:
        return


def update_podcasts(all_update: bool = True) -> None:
    """
    This is for refreshing our stored podcasts so we can grab new episodes if we want.
    We can do all or pick one.
    """
    config, _ = init_config()
    shows = parse_podcast_list(config)
    if not shows:
        console.print(Panel("We have no podcasts in config, so we can't update anything.", style="yellow"))
        return

    if all_update:
        console.print(Panel("Doing a full update of all stored podcasts...", style="magenta"))
        for link, name_id, out_dir in shows:
            console.print(Panel(f"Updating '{name_id}'", style="cyan"))
            download_podcast_rss(link, out_dir, count=None, verbose=False)
        console.print(Panel("All updates complete!", style="green"))
    else:
        name_map = {f"{i+1}) {s[1]}": i for i, s in enumerate(shows)}
        selection = questionary.select(
            "Pick the one you want to update:",
            choices=list(name_map.keys()),
            style=custom_style
        ).ask()
        if not selection:
            return
        idx = name_map[selection]
        link, showname, outd = shows[idx]
        console.print(Panel(f"Updating '{showname}' now...", style="cyan"))
        download_podcast_rss(link, outd, count=None, verbose=False)
        console.print(Panel("Done updating that podcast!", style="green"))


def menu_download() -> None:
    """This is where we pick to either download from stored shows or from a custom RSS URL."""
    config, _ = init_config()
    choice = questionary.select(
        "Download Menu:",
        choices=["From stored podcasts", "Enter custom RSS", "Return"],
        style=custom_style
    ).ask()

    if choice == "From stored podcasts":
        pods = parse_podcast_list(config)
        if not pods:
            console.print(Panel("No stored podcasts found.", style="yellow"))
            return
        name_ids = [p[1] for p in pods]
        selection = questionary.select(
            "Choose a stored podcast to download from:",
            choices=name_ids,
            style=custom_style
        ).ask()
        if not selection:
            return

        link, showname, outd = [(l, n, d) for (l, n, d) in pods if n == selection][0]
        oldest = questionary.confirm(
            "Download oldest episodes first?",
            default=False,
            style=custom_style
        ).ask()

        cstr = questionary.text(
            "How many episodes do you want? (blank=all)",
            style=custom_style
        ).ask()
        limit = int(cstr) if cstr and cstr.isdigit() else None

        srch = questionary.text(
            "Search term to match in titles? (blank=none)",
            style=custom_style
        ).ask()

        log_yn = questionary.confirm(
            "Want to enable file logging?",
            default=False,
            style=custom_style
        ).ask()
        verb = questionary.confirm(
            "Verbose output (show server info, speeds, etc.)?",
            default=False,
            style=custom_style
        ).ask()

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

    elif choice == "Enter custom RSS":
        rss_url = questionary.text("RSS URL:", style=custom_style).ask()
        if not rss_url:
            console.print(Panel("Not a valid URL. Stopping.", style="red"))
            return

        fmt = questionary.select(
            "Pick a filename format:",
            choices=["default", "daily"],
            style=custom_style
        ).ask()

        oldest = questionary.confirm("Download oldest first?", default=False, style=custom_style).ask()
        cstr = questionary.text("How many episodes? (blank=all):", style=custom_style).ask()
        limit = int(cstr) if cstr and cstr.isdigit() else None

        srch = questionary.text("Title search term? (blank=none):", style=custom_style).ask()
        def_out = config["system"].get("default_output_dir", DEFAULT_OUTPUT_DIR)
        outdir = questionary.text("Output folder:", default=def_out, style=custom_style).ask()

        log_yn = questionary.confirm(
            "Enable file logging?",
            default=False,
            style=custom_style
        ).ask()
        verb = questionary.confirm(
            "Verbose output?",
            default=False,
            style=custom_style
        ).ask()

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
    else:
        return


###############################################################################
#                                   MAIN APP                                  #
###############################################################################

def main() -> None:
    config, _ = init_config()

    console.print(Panel(f"=== prx {VERSION} ===", style="bold magenta"))

    while True:
        selection = questionary.select(
            "Main Menu:",
            choices=[
                "Update TDZ",
                "Browse Local Files",
                "Settings",
                "About",
                "Exit"
            ],
            style=custom_style
        ).ask()

        if selection == "Download Podcasts":
            menu_download()

        elif selection == "Update TDZ":
            choice = questionary.select(
                "Update Options:",
                choices=["Update TDZ", "Return"],
                style=custom_style
            ).ask()
            if choice == "Update TDZ":
                update_podcasts(all_update=True)
            else:
                pass

        elif selection == "Browse Local Files":
            browse_local_files()

        elif selection == "Settings":
            subsel = questionary.select(
                "Settings Menu:",
                choices=[
                    "Init (create/load prx.ini)",
                    "Manage config (view/edit)",
                    "Manage podcasts list",
                    "Return"
                ],
                style=custom_style
            ).ask()
            if subsel == "Init (create/load prx.ini)":
                handle_init_command()
            elif subsel == "Manage config (view/edit)":
                manage_settings_config()
            elif subsel == "Manage podcasts list":
                manage_podcasts_in_config()
            else:
                pass

        elif selection == "About":
            about_choice = questionary.select(
                "About:",
                choices=["Show version", "Return"],
                style=custom_style
            ).ask()
            if about_choice == "Show version":
                console.print(
                    Panel(
                        f"prx {VERSION}\n"
                        "A TUI-based podcast downloader that I put together, with local browsing, date parsing, "
                        "and a brand-new vibe. Enjoy!",
                        style="green"
                    )
                )
            else:
                pass

        else:  # "Exit"
            console.print(Panel("Exiting program... Thanks for using prx!", style="bold magenta"))
            break

    console.print(Panel("=== All done. Bye! ===", style="bold magenta"))


if __name__ == "__main__":
    main()
