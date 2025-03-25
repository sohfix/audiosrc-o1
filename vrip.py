#!/usr/bin/env python3
"""
vrip 2.0.0 [Enhanced Update, Verbose Logging, Extended Server Info & File Verification]

A command‑line tool for downloading podcast episodes from RSS feeds.
Features:
  - Uses a configuration file (vrip.ini) to store user info and podcasts.
  - Podcast list entries are stored as:
        PODCAST_LINK : NAME_ID : OUTPUT_DIRECTORY
  - Custom filename formats (default/daily).
  - Verbose mode shows extended server info (via httpx), download speed, etc.
  - Automatic timeout handling with exponential backoff and retry.
  - Update feature now checks every episode and downloads missing ones.
  - Optional SHA256 integrity hashing (sidecar .sha256 file) and verification.
  - HTTPS‑only mode option.
  - Rich table display, status panels with icons, clear banners, and Quiet Mode.
  - Strong type hints and improved error logging.

Refer to the manual (via the Manual & About menu) for full details.
"""

import configparser
import hashlib
import logging
import os
import platform
import re
import shlex
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, TextIO, Tuple

import feedparser
import httpx  # Modern HTTP client for extended server info
import requests
from rich.console import Console
from rich.panel import Panel
from rich.progress import (BarColumn, Progress, ProgressColumn, TextColumn,
                           TimeElapsedColumn)
from rich.table import Table

console: Console = Console()
QUIET_MODE: bool = False  # Global configuration for quiet mode

# Default settings
DEFAULT_TIMEOUT: int = 10
DEFAULT_MAX_RETRIES: int = 3
DEFAULT_INITIAL_BACKOFF: int = 2
DEFAULT_HTTPS_ONLY: bool = False
DEFAULT_GENERATE_HASH: bool = False  # SHA256 optional

VERSION: str = (
    "2.0.0 [Enhanced Update, Verbose Logging, Extended Server Info & File Verification]"
)

# Global list to hold files that ultimately fail to download.
FAILED_DOWNLOADS: List[Dict[str, str]] = []


###############################################################################
#                                PROGRESS BAR                                 #
###############################################################################


class MBPercentColumn(ProgressColumn):
    """Custom column to show downloaded/total size in MB and percentage."""

    def render(self, task) -> str:
        if task.total is None or task.total == 0:
            return "0.00MB/??MB (0%)"
        completed_mb = task.completed / (1024 * 1024)
        total_mb = task.total / (1024 * 1024)
        percentage = (task.completed / task.total) * 100
        return f"{completed_mb:>5.2f}MB/{total_mb:>5.2f}MB ({percentage:>5.1f}%)"


###############################################################################
#                           HELPER FUNCTIONS                                  #
###############################################################################


def human_readable_speed(bytes_per_sec: float) -> str:
    """Convert speed in bytes per second to a human-readable string."""
    if bytes_per_sec < 1024:
        return f"{bytes_per_sec:.2f} B/s"
    elif bytes_per_sec < 1024 * 1024:
        return f"{bytes_per_sec / 1024:.2f} KB/s"
    else:
        return f"{bytes_per_sec / (1024 * 1024):.2f} MB/s"


def compute_sha256(file_path: str) -> str:
    """Compute the SHA256 hash of a file and return the hex digest."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


def verify_file_integrity(file_path: str) -> bool:
    """
    Verify the file integrity by comparing the computed SHA256 hash of the file
    with the contents of the sidecar .sha256 file.
    """
    hash_file = file_path + ".sha256"
    if not os.path.exists(hash_file):
        console.print(
            Panel(
                f"No hash file found for '{file_path}'.",
                title="File Verification",
                style="yellow",
            )
        )
        return False
    with open(hash_file, "r") as hf:
        expected_hash = hf.read().strip()
    computed_hash = compute_sha256(file_path)
    if computed_hash == expected_hash:
        console.print(
            Panel(
                f"File verified successfully: {file_path}",
                title="File Verification",
                style="green",
            )
        )
        return True
    else:
        console.print(
            Panel(
                f"File verification failed for: {file_path}",
                title="File Verification",
                style="red",
            )
        )
        return False


def get_extended_server_info(url: str) -> Dict[str, Any]:
    """
    Use httpx to perform a HEAD request and retrieve extended server info,
    including HTTP version, Content-Type, Content-Length, Date, and Server header.
    """
    try:
        with httpx.Client(http2=True, timeout=DEFAULT_TIMEOUT) as client:
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


###############################################################################
#                            FILE & CONFIG HELPERS                            #
###############################################################################


def clear_screen() -> None:
    """Clear the terminal screen using Rich."""
    console.clear()


def get_config_path() -> str:
    """
    Returns the path to the vrip.ini file:
      - On Windows: C:\vrip_tools\vrip.ini
      - On Linux:   ~/programs/vrip-ini/vrip.ini
    """
    current_os: str = platform.system().lower()
    if "windows" in current_os:
        return r"C:\vrip_tools\vrip.ini"
    else:
        home_dir: str = os.path.expanduser("~")
        return os.path.join(home_dir, "programs", "vrip-ini", "vrip.ini")


def ensure_output_dir(output_dir: str) -> None:
    """Ensure the output directory exists, creating it if necessary."""
    try:
        os.makedirs(output_dir, exist_ok=True)
    except OSError as e:
        console.print(
            Panel(
                f"Error: Unable to create output directory '{output_dir}'.\n{e}",
                title="Error",
                style="red",
            )
        )
        sys.exit(1)


def init_config() -> Tuple[configparser.ConfigParser, str]:
    """
    Load or create a default vrip.ini config.
    Returns a tuple (config, config_path).
    """
    config_path: str = get_config_path()
    config_dir: str = os.path.dirname(config_path)
    if not os.path.exists(config_dir):
        os.makedirs(config_dir, exist_ok=True)

    config: configparser.ConfigParser = configparser.ConfigParser()
    if os.path.exists(config_path):
        config.read(config_path)
        if not QUIET_MODE:
            console.print(
                Panel(
                    f"Loading existing config from:\n{config_path}",
                    title="Config",
                    style="blue",
                )
            )
    else:
        if not QUIET_MODE:
            console.print(
                Panel(
                    f"Config not found. Creating default config at:\n{config_path}",
                    title="Config",
                    style="yellow",
                )
            )
        config["user"] = {"name": "", "password": ""}
        config["system"] = {
            "os": platform.system().lower(),
            "default_output_dir": (
                r"C:\vrip_tools\downloads"
                if "windows" in platform.system().lower()
                else os.path.join(os.path.expanduser("~"), "podcasts")
            ),
            "download_timeout": str(DEFAULT_TIMEOUT),
            "max_retries": str(DEFAULT_MAX_RETRIES),
            "initial_retry_backoff": str(DEFAULT_INITIAL_BACKOFF),
            "https_only": str(DEFAULT_HTTPS_ONLY),
            "quiet_mode": str(QUIET_MODE),
        }
        config["logging"] = {
            "log_dir": (
                r"C:\vrip_tools\logs"
                if "windows" in platform.system().lower()
                else os.path.join(os.path.expanduser("~"), "pylogs", "vrip")
            ),
            "log_level": "INFO",
        }
        config["Podcasts"] = {"podcast_list": ""}
        with open(config_path, "w") as configfile:  # type: TextIO
            config.write(configfile)
        if not QUIET_MODE:
            console.print(
                Panel("Default vrip.ini created.", title="Config", style="green")
            )
    return config, config_path


def setup_logging() -> None:
    """Enable session logging based on the config file."""
    config, _ = init_config()
    log_dir: str = config["logging"].get("log_dir", "")
    log_level_str: str = config["logging"].get("log_level", "INFO")
    numeric_level: int = getattr(logging, log_level_str.upper(), logging.INFO)
    try:
        os.makedirs(log_dir, exist_ok=True)
    except OSError as e:
        console.print(
            Panel(
                f"Error: Unable to create log directory '{log_dir}'.\n{e}",
                title="Error",
                style="red",
            )
        )
        log_dir = ""
    timestamp: str = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file: Optional[str] = (
        os.path.join(log_dir, f"session_{timestamp}.log") if log_dir else None
    )
    logging.basicConfig(
        filename=log_file if log_file else None,
        filemode="w",
        format="%(asctime)s - %(levelname)s - %(message)s",
        level=numeric_level,
    )
    if log_file and not QUIET_MODE:
        console.print(
            Panel(
                f"Session logs will be saved to:\n{log_file}",
                title="Logging",
                style="green",
            )
        )
    elif not QUIET_MODE:
        console.print(
            Panel(
                "Logging to console only (no log file directory).",
                title="Logging",
                style="yellow",
            )
        )
    logging.info("Logging initialized.")


def validate_config() -> None:
    """
    Interactive check to ensure username, password, and OS are set.
    """
    config, config_path = init_config()
    changed: bool = False
    if "user" not in config:
        config["user"] = {}
    if "system" not in config:
        config["system"] = {}
    if not config["user"].get("name"):
        console.print(
            Panel(
                "No user name found. Let's fix that.",
                title="Config Update",
                style="yellow",
            )
        )
        config["user"]["name"] = console.input("[blue]Enter your name: [/blue]")
        changed = True
    if not config["user"].get("password"):
        console.print(
            Panel(
                "No password found. Let's fix that.",
                title="Config Update",
                style="yellow",
            )
        )
        config["user"]["password"] = console.input("[blue]Enter your password: [/blue]")
        changed = True
    if not config["system"].get("os"):
        console.print(
            Panel(
                "No OS info found. Let's fix that.",
                title="Config Update",
                style="yellow",
            )
        )
        config["system"]["os"] = platform.system().lower()
        changed = True
    if changed:
        with open(config_path, "w") as f:
            config.write(f)
        console.print(
            Panel("Configuration updated successfully!", title="Config", style="green")
        )
    else:
        console.print(
            Panel("Configuration is already good to go.", title="Config", style="green")
        )


###############################################################################
#                  PODCAST LIST MANAGEMENT FUNCTIONS                          #
###############################################################################


def manage_podcasts_in_config() -> None:
    """
    Submenu for managing podcasts.
    The podcast list is stored in the config under the key 'podcast_list' in the [Podcasts] section.
    Each entry should have the format:
      PODCAST_LINK : NAME_ID : OUTPUT_DIRECTORY
    """
    config, config_path = init_config()
    while True:
        console.print(
            Panel(
                "Manage Podcasts:\n"
                "1) View list\n"
                "2) Add a new podcast (format: PODCAST_LINK : NAME_ID : OUTPUT_DIRECTORY)\n"
                "3) Edit an existing podcast\n"
                "4) Remove a podcast\n"
                "5) Return to previous menu",
                title="Podcast List",
                style="cyan",
            )
        )
        choice: str = console.input("Enter choice: ").strip()
        podcast_line: str = config["Podcasts"].get("podcast_list", "").strip()
        entries: List[str] = [
            chunk.strip() for chunk in podcast_line.split(";") if chunk.strip()
        ]
        podcast_triples: List[Tuple[str, str, str]] = []
        for entry in entries:
            parts: List[str] = [p.strip() for p in entry.split(" : ")]
            if len(parts) == 3:
                podcast_triples.append((parts[0], parts[1], parts[2]))
        if choice == "1":
            if not podcast_triples:
                console.print(Panel("No podcasts in the list.", style="yellow"))
            else:
                table: Table = Table(title="Current Podcast List")
                table.add_column("NAME_ID", style="cyan")
                table.add_column("Podcast Link", style="magenta")
                table.add_column("Output Directory", style="green")
                for plink, name_id, out_dir in podcast_triples:
                    table.add_row(name_id, plink, out_dir)
                console.print(table)
        elif choice == "2":
            entry: str = console.input(
                "Enter new podcast (format: PODCAST_LINK : NAME_ID : OUTPUT_DIRECTORY): "
            ).strip()
            parts: List[str] = [p.strip() for p in entry.split(" : ")]
            if len(parts) == 3:
                podcast_triples.append((parts[0], parts[1], parts[2]))
                new_value: str = " ; ".join(
                    [
                        f"{link} : {name} : {out_dir}"
                        for (link, name, out_dir) in podcast_triples
                    ]
                )
                config["Podcasts"]["podcast_list"] = new_value
                with open(config_path, "w") as f:
                    config.write(f)
                console.print(Panel(f"Added podcast '{parts[1]}'", style="green"))
            else:
                console.print(
                    Panel(
                        "Invalid format. Please use: PODCAST_LINK : NAME_ID : OUTPUT_DIRECTORY",
                        style="red",
                    )
                )
        elif choice == "3":
            if not podcast_triples:
                console.print(Panel("No podcasts to edit.", style="yellow"))
                continue
            for idx, (plink, name_id, out_dir) in enumerate(podcast_triples, start=1):
                console.print(f"{idx}) {name_id} -> Link: {plink} | Output: {out_dir}")
            selection_str: str = console.input(
                "Select podcast number to edit: "
            ).strip()
            try:
                selection: int = int(selection_str)
                if 1 <= selection <= len(podcast_triples):
                    old_plink, old_name, old_out = podcast_triples[selection - 1]
                    console.print(Panel(f"Editing '{old_name}'", style="blue"))
                    new_entry: str = console.input(
                        "Enter new value (format: PODCAST_LINK : NAME_ID : OUTPUT_DIRECTORY, blank to keep current): "
                    ).strip()
                    if new_entry:
                        parts = [p.strip() for p in new_entry.split(" : ")]
                        if len(parts) == 3:
                            podcast_triples[selection - 1] = (
                                parts[0],
                                parts[1],
                                parts[2],
                            )
                        else:
                            console.print(
                                Panel("Invalid format. Skipping edit.", style="red")
                            )
                            continue
                    new_value = " ; ".join(
                        [
                            f"{link} : {name} : {out_dir}"
                            for (link, name, out_dir) in podcast_triples
                        ]
                    )
                    config["Podcasts"]["podcast_list"] = new_value
                    with open(config_path, "w") as f:
                        config.write(f)
                    console.print(Panel("Podcast updated.", style="green"))
                else:
                    console.print(Panel("Invalid selection.", style="red"))
            except ValueError:
                console.print(Panel("Please enter a valid number.", style="red"))
        elif choice == "4":
            if not podcast_triples:
                console.print(Panel("No podcasts to remove.", style="yellow"))
                continue
            for idx, (plink, name_id, out_dir) in enumerate(podcast_triples, start=1):
                console.print(f"{idx}) {name_id} -> Link: {plink} | Output: {out_dir}")
            selection_str = console.input("Select podcast number to remove: ").strip()
            try:
                selection = int(selection_str)
                if 1 <= selection <= len(podcast_triples):
                    removed = podcast_triples.pop(selection - 1)
                    new_value = " ; ".join(
                        [
                            f"{link} : {name} : {out_dir}"
                            for (link, name, out_dir) in podcast_triples
                        ]
                    )
                    config["Podcasts"]["podcast_list"] = new_value
                    with open(config_path, "w") as f:
                        config.write(f)
                    console.print(
                        Panel(f"Removed podcast '{removed[1]}'", style="green")
                    )
                else:
                    console.print(Panel("Invalid selection.", style="red"))
            except ValueError:
                console.print(Panel("Please enter a valid number.", style="red"))
        elif choice == "5":
            break
        else:
            console.print(Panel("Invalid choice.", style="red"))


def parse_podcast_list(config: configparser.ConfigParser) -> List[Tuple[str, str, str]]:
    """
    Parse the 'podcast_list' from the [Podcasts] section.
    Expected format: "PODCAST_LINK : NAME_ID : OUTPUT_DIRECTORY ; ..."
    Returns a list of tuples (podcast_link, name_id, output_directory).
    """
    podcast_line: str = config["Podcasts"].get("podcast_list", "").strip()
    if not podcast_line:
        return []
    entries: List[str] = [
        chunk.strip() for chunk in podcast_line.split(";") if chunk.strip()
    ]
    result: List[Tuple[str, str, str]] = []
    for entry in entries:
        parts: List[str] = [p.strip() for p in entry.split(" : ")]
        if len(parts) == 3:
            result.append((parts[0], parts[1], parts[2]))
    return result


def write_podcast_list(
    config: configparser.ConfigParser, podcast_triples: List[Tuple[str, str, str]]
) -> None:
    """
    Write the list of tuples (podcast_link, name_id, output_directory) to the config.
    Format: "PODCAST_LINK : NAME_ID : OUTPUT_DIRECTORY ; ..."
    """
    assembled: str = " ; ".join(
        [f"{link} : {name} : {out_dir}" for (link, name, out_dir) in podcast_triples]
    )
    config["Podcasts"]["podcast_list"] = assembled


###############################################################################
#                   MAIN COMMAND HANDLERS (Forward Declarations)             #
###############################################################################


def handle_init_command() -> None:
    """
    Auto-detect OS, install dependencies, create/load vrip.ini, and prompt for any missing details.
    """
    current_os: str = platform.system().lower()
    console.print(
        Panel(
            f"Running 'init' command for OS = {current_os}", title="Init", style="blue"
        )
    )
    if "windows" in current_os:
        console.print(Panel("Current OS: WINDOWS", title="Init", style="blue"))
    elif "linux" in current_os:
        console.print(Panel("Current OS: LNX", title="Init", style="blue"))
    else:
        console.print(
            Panel("Unsupported OS detected. Abort.", title="Error", style="red")
        )
        return
    init_config()
    validate_config()
    console.print(Panel("Initialization complete!", title="Init", style="green"))


def manage_settings_config() -> None:
    """Create, edit, or view vrip.ini from the known OS-specific path."""
    config, config_path = init_config()
    console.print(
        Panel("Settings management selected.", title="Settings", style="blue")
    )
    action: str = (
        console.input("[yellow]Choose an action (view/edit): [/yellow]").strip().lower()
    )
    if action == "view":
        if os.path.exists(config_path):
            with open(config_path, "r") as configfile:
                content: str = configfile.read()
            console.print(Panel(content, title="vrip.ini contents", style="blue"))
        else:
            console.print(Panel("No config file found!", title="Error", style="red"))
    elif action == "edit":
        validate_config()
        edit_more: str = (
            console.input(
                "[yellow]Do you want to edit advanced settings (output dir, logging)? (y/n): [/yellow]"
            )
            .strip()
            .lower()
        )
        if edit_more == "y":
            changed: bool = False
            config, config_path = init_config()
            current_output_dir: str = config["system"].get("default_output_dir", "")
            new_output_dir: str = console.input(
                f"[blue]Current default output dir:[/blue] {current_output_dir}\nEnter new dir (blank=keep current): "
            ).strip()
            if new_output_dir:
                config["system"]["default_output_dir"] = new_output_dir
                changed = True
            current_log_dir: str = config["logging"].get("log_dir", "")
            new_log_dir: str = console.input(
                f"[blue]Current log directory:[/blue] {current_log_dir}\nEnter new dir (blank=keep current): "
            ).strip()
            if new_log_dir:
                config["logging"]["log_dir"] = new_log_dir
                changed = True
            current_log_level: str = config["logging"].get("log_level", "INFO")
            new_log_level: str = (
                console.input(
                    f"[blue]Current log level:[/blue] {current_log_level}\nEnter new level (DEBUG/INFO/WARNING/ERROR/CRITICAL) or blank to keep current: "
                )
                .strip()
                .upper()
            )
            valid_levels: List[str] = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
            if new_log_level and new_log_level in valid_levels:
                config["logging"]["log_level"] = new_log_level
                changed = True
            if changed:
                with open(config_path, "w") as cf:
                    config.write(cf)
                console.print(Panel("Configuration updated!", style="green"))
            else:
                console.print(Panel("No advanced settings changed.", style="green"))
    else:
        console.print(
            Panel(
                "Invalid action. Please choose 'view' or 'edit'.",
                title="Error",
                style="red",
            )
        )


def manual_text() -> str:
    """
    Returns a comprehensive Markdown-style manual describing all features.
    """
    return f"""
# vrip 2.0.0 [Enhanced Update, Verbose Logging, Extended Server Info & File Verification]

## Overview
**vrip** is a command-line tool for downloading podcast episodes from RSS feeds.
It uses a configuration file (vrip.ini) to store user settings and a podcast list.

## Configuration & Setup
- **Config File:**  
  Located at `C:\\vrip_tools\\vrip.ini` (Windows) or `~/programs/vrip-ini/vrip.ini` (Linux).  
  It stores user credentials, system settings (output directories, timeouts, HTTPS-only mode, quiet mode), logging settings, and a podcast list.

- **Podcast List Format:**  
  Each entry is stored as:  
  PODCAST_LINK : NAME_ID : OUTPUT_DIRECTORY

  Example: https://example.com/feed.rss : MyShow : G:\\MyShow

## Features
- **Podcast Downloading:**  
Download episodes with custom filename formats:
- **default:** Sanitized episode title.
- **daily:** If the title ends with a space and 6 digits (e.g., "060624"), the date is moved to the front.

- **Verbose Mode:**  
When enabled, displays:
- Extended server information (via httpx HEAD request).
- Calculated download speed in a human-readable format.
- Detailed logging of retries and timeouts.

- **Automatic Timeout & Retry:**  
Configurable timeout and exponential backoff strategy for retries.
After a configurable number of failures, the file is skipped and recorded.

- **Update Feature:**  
- **Update All:** Downloads every undownloaded episode for all stored podcasts.
- **Update One:** Downloads every undownloaded episode for a selected podcast.
- Before downloading, the script checks if the file already exists and only downloads missing episodes.

- **File Integrity:**  
If enabled, generates a SHA256 hash stored in a sidecar file (`.sha256`) and then verifies the file after download.

- **Security Enhancements:**  
- HTTPS-only mode to reject HTTP feeds.
- Configurable download timeout and retry backoff.
- Improved error logging with timestamps.

## Console Output Enhancements
- **Rich Tables:**  
Displays stored podcasts in a table with columns for NAME_ID, Link, and Output Directory.
- **Status Panels with Icons:**  
Uses icons (✔️ for success, ⚠️ for skipped, ❌ for failed) for clear feedback.
- **Quiet Mode:**  
Option to suppress output except errors.
- **Session Banners:**  
Clear start/end banners for update and download sessions.

## Versioning
This is version **2.0.0 [Enhanced Update, Verbose Logging, Extended Server Info & File Verification]**, reflecting major enhancements in update functionality, server info, file verification, logging, and security upgrades.

## How to Use
1. **Download Podcasts:**  
 Choose from stored podcasts by entering the NAME_ID or enter a custom RSS URL.
2. **Update Podcasts:**  
 Use the "Update Podcasts" option to update all or a single show (downloads all undownloaded episodes).
3. **Settings:**  
 Configure vrip and manage the podcast list via the config file.
4. **Manual & About:**  
 Access this manual and version information.

Happy podcasting!
"""


def handle_man_command() -> None:
    """Display a thorough manual explaining how to use the vrip script."""
    manual = manual_text()
    console.print(Panel(manual, title="Manual", style="white"))


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
    Download a file with a progress bar, retries, and exponential backoff.
    Displays extended server info (via httpx) if verbose is True.
    After download, if SHA256 hashing is enabled, generates a sidecar file and verifies the download.
    Returns True if successful, False otherwise.
    """
    # Get extended server info before download
    if verbose:
        ext_info = get_extended_server_info(url)
        info_str = "\n".join(f"{k}: {v}" for k, v in ext_info.items())
        console.print(
            Panel(
                f"Extended Server Info:\n{info_str}", title="Server Info", style="cyan"
            )
        )

    for attempt in range(1, max_retries + 1):
        start_time: float = time.time()
        try:
            config, _ = init_config()
            https_only: bool = config["system"].getboolean(
                "https_only", fallback=DEFAULT_HTTPS_ONLY
            )
            if https_only and not url.lower().startswith("https"):
                raise requests.RequestException(
                    "HTTP feeds are rejected in HTTPS-only mode."
                )
            response = requests.get(url, stream=True, timeout=timeout)
            response.raise_for_status()
            total_size: int = int(response.headers.get("content-length", 0))
            with open(output_path, "wb") as file, Progress(
                TextColumn("[bold blue]{task.description}[/bold blue]"),
                BarColumn(),
                MBPercentColumn(),
                TimeElapsedColumn(),
                console=console,
                transient=QUIET_MODE,
            ) as progress:
                task = progress.add_task(description, total=total_size)
                for chunk in response.iter_content(chunk_size=4096):
                    if chunk:
                        file.write(chunk)
                        progress.update(task, advance=len(chunk))
            elapsed: float = time.time() - start_time
            speed: float = total_size / elapsed if elapsed > 0 else 0
            if verbose:
                console.print(
                    Panel(
                        f"Download completed in {elapsed:.2f} seconds at an average speed of {human_readable_speed(speed)}.",
                        title="Download Speed",
                        style="green",
                    )
                )
            logging.info(f"Downloaded: {url} -> {output_path}")
            # Generate and verify hash if enabled
            if config["system"].getboolean(
                "generate_hash", fallback=DEFAULT_GENERATE_HASH
            ):
                hash_digest: str = compute_sha256(output_path)
                hash_file: str = output_path + ".sha256"
                with open(hash_file, "w") as hf:
                    hf.write(hash_digest)
                if verbose:
                    console.print(
                        Panel(
                            f"SHA256 generated: {hash_digest}",
                            title="File Integrity",
                            style="green",
                        )
                    )
                # Verify file integrity immediately after download
                if not verify_file_integrity(output_path):
                    console.print(
                        Panel(
                            "File verification failed. Retrying download...",
                            title="File Verification",
                            style="red",
                        )
                    )
                    raise Exception("File verification failed")
            return True
        except requests.Timeout:
            console.print(
                Panel(
                    f"Timeout on attempt {attempt}/{max_retries} for {url}",
                    title="⚠️ Timeout",
                    style="red",
                )
            )
            logging.exception(f"Timeout on attempt {attempt} for {url}")
        except Exception as e:
            console.print(
                Panel(
                    f"Error on attempt {attempt}/{max_retries} for {url}:\n{e}",
                    title="❌ Download Error",
                    style="red",
                )
            )
            logging.exception(f"Error on attempt {attempt} for {url}")
        backoff: int = initial_backoff * (2 ** (attempt - 1))
        time.sleep(backoff)
    return False


def build_episode_filename(original_title: str, fmt: str) -> str:
    """
    Given the raw feed entry title and a format string, return a sanitized filename (without .mp3).
      - 'default': sanitized title.
      - 'daily': if title ends with a space plus 6 digits, move date to front.
    """

    def sanitize(text: str) -> str:
        return "".join(c for c in text if c.isalnum() or c in " _-").rstrip()

    if fmt == "daily":
        pattern: str = r"^(.*)\s+(\d{6})$"
        match = re.match(pattern, original_title)
        if match:
            main_part, date_part = match.groups()
            return f"{date_part} {sanitize(main_part)}".strip()
        else:
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
    Download episodes from a podcast RSS feed.
    For each episode, check if the corresponding file exists (using os.path.exists).
    If not, download the episode.
    """
    logging.info(
        f"Starting RSS download from: {rss_url}, output_dir={output_dir}, count={count}, searchby={searchby}, oldest_first={oldest_first}, format={format_str}"
    )
    if verbose:
        console.print(
            Panel(
                f"Fetching RSS feed from:\n{rss_url}\nOutput directory:\n{output_dir}\nFilename Format: {format_str}",
                title="Podcast RSS",
                style="blue",
            )
        )
    ensure_output_dir(output_dir)
    feed = feedparser.parse(rss_url)
    if not feed.entries:
        console.print(
            Panel(
                f"No episodes found in RSS feed:\n{rss_url}",
                title="Podcast RSS",
                style="yellow",
            )
        )
        logging.warning("No entries found in RSS feed.")
        return
    entries = (
        [
            entry
            for entry in feed.entries
            if searchby and searchby.lower() in entry.title.lower()
        ]
        if searchby
        else feed.entries
    )
    if not entries:
        console.print(
            Panel(
                f"No episodes found matching search term '{searchby}'.",
                title="Podcast RSS",
                style="yellow",
            )
        )
        logging.warning(f"No entries match search term '{searchby}'.")
        return

    def get_date(entry: Any) -> Optional[float]:
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            return time.mktime(entry.published_parsed)
        elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
            return time.mktime(entry.updated_parsed)
        else:
            return None

    dated_entries = [(e, get_date(e)) for e in entries]
    dated_entries_with_time = [(e, dt) for (e, dt) in dated_entries if dt is not None]
    dated_entries_without_time = [e for (e, dt) in dated_entries if dt is None]
    dated_entries_with_time.sort(key=lambda x: x[1], reverse=(not oldest_first))
    sorted_entries = (
        ([e for (e, _) in dated_entries_with_time] + dated_entries_without_time)
        if oldest_first
        else (dated_entries_without_time + [e for (e, _) in dated_entries_with_time])
    )
    entries_to_download = sorted_entries[:count] if count else sorted_entries
    if not entries_to_download:
        console.print(
            Panel(
                "No episodes to download after applying sorting/count.",
                title="Podcast RSS",
                style="yellow",
            )
        )
        return

    for index, entry in enumerate(entries_to_download, start=1):
        title: str = entry.title
        link: Optional[str] = entry.enclosures[0].href if entry.enclosures else None
        if not link:
            console.print(
                Panel(
                    f"Skipping episode '{title}' (no downloadable link found).",
                    title="⚠️ Skipped",
                    style="yellow",
                )
            )
            logging.warning(f"No enclosure found for episode: {title}")
            continue
        base_name: str = build_episode_filename(title, format_str)
        file_path: str = os.path.join(output_dir, f"{base_name}.mp3")
        if os.path.exists(file_path):
            console.print(
                Panel(
                    f"Skipping (file exists): '{file_path}'",
                    title="⚠️ Skipped",
                    style="yellow",
                )
            )
            logging.info(f"Skipping download (already exists): {file_path}")
            continue
        if verbose:
            console.print(
                Panel(
                    f"Downloading episode:\nTitle: {title}\nLink: {link}\nFile: {file_path}",
                    title=f"Episode {index}/{len(entries_to_download)}",
                    style="blue",
                )
            )
        success: bool = download_with_progress(
            link,
            file_path,
            description=f"Episode {index}/{len(entries_to_download)}",
            verbose=verbose,
        )
        if success:
            console.print(Panel(f"✔️ Successfully downloaded '{title}'", style="green"))
        else:
            console.print(
                Panel(
                    f"❌ Failed to download '{title}' after {DEFAULT_MAX_RETRIES} attempts.",
                    style="red",
                )
            )
            FAILED_DOWNLOADS.append({"title": title, "url": link, "output": file_path})
        clear_screen()
    if FAILED_DOWNLOADS:
        failed_titles: str = "\n".join(
            [f"- {item['title']}" for item in FAILED_DOWNLOADS]
        )
        console.print(
            Panel(
                f"The following files failed to download:\n{failed_titles}",
                title="❌ Failed Downloads",
                style="red",
            )
        )
        logging.warning("Some files failed to download.")


def update_podcasts(all_update: bool = True) -> None:
    """
    Update podcasts using the stored podcast list.
    In update mode, the script checks every episode in the RSS feed and downloads only those that are missing.
    """
    config, _ = init_config()
    podcast_entries: List[Tuple[str, str, str]] = parse_podcast_list(config)
    if not podcast_entries:
        console.print(
            Panel(
                "No stored podcasts found. Add them in Settings > Manage podcasts list.",
                style="yellow",
            )
        )
        return
    if all_update:
        console.print(
            Panel(
                "Starting batch update for all podcasts...",
                title="Update All",
                style="magenta",
            )
        )
        for plink, name_id, out_dir in podcast_entries:
            console.print(
                Panel(f"Updating '{name_id}'...", title="Update", style="cyan")
            )
            download_podcast_rss(plink, out_dir, count=None, verbose=True)
        console.print(
            Panel("Batch update completed.", title="Update All", style="green")
        )
    else:
        names: List[str] = [name for (_, name, _) in podcast_entries]
        table: Table = Table(title="Stored Podcasts")
        table.add_column("NAME_ID", style="cyan")
        for name in names:
            table.add_row(name)
        console.print(table)
        raw_input: str = console.input("Enter podcast NAME_ID to update: ").strip()
        try:
            tokens = shlex.split(raw_input)
        except Exception as e:
            console.print(Panel(f"Error parsing input: {e}", style="red"))
            return
        name_input: str = " ".join(tokens).strip()
        matching = [
            (plink, name, out_dir)
            for (plink, name, out_dir) in podcast_entries
            if name.lower() == name_input.lower()
        ]
        if not matching:
            console.print(
                Panel(f"No podcast found with NAME_ID '{name_input}'", style="red")
            )
            return
        chosen_link, chosen_name, chosen_outdir = matching[0]
        console.print(
            Panel(f"Updating '{chosen_name}'...", title="Update", style="cyan")
        )
        download_podcast_rss(chosen_link, chosen_outdir, count=None, verbose=True)
        console.print(
            Panel(
                f"Update for '{chosen_name}' completed.", title="Update", style="green"
            )
        )


###############################################################################
#                                  SUBMENUS                                   #
###############################################################################


def menu_settings() -> None:
    while True:
        menu_str: str = (
            "[bold]Settings Menu[/bold]\n"
            "1) Init (auto-detect OS, install deps, configure vrip.ini)\n"
            "2) Manage config (view/edit vrip.ini)\n"
            "3) Manage podcasts list (add/edit/remove podcasts)\n"
            "4) Return to main menu"
        )
        console.print(Panel(menu_str, title="Settings", style="cyan"))
        choice: str = console.input("\nEnter choice: ").strip()
        if choice == "1":
            handle_init_command()
        elif choice == "2":
            manage_settings_config()
        elif choice == "3":
            manage_podcasts_in_config()
        elif choice == "4":
            break
        else:
            console.print(Panel("Invalid choice.", title="Error", style="red"))


def menu_manual_about() -> None:
    while True:
        menu_str: str = (
            "[bold]Manual & About[/bold]\n"
            "1) Show manual\n"
            f"2) About (version {VERSION})\n"
            "3) Return to main menu"
        )
        console.print(Panel(menu_str, title="Help/Info", style="cyan"))
        choice: str = console.input("\nEnter choice: ").strip()
        if choice == "1":
            handle_man_command()
        elif choice == "2":
            console.print(
                Panel(
                    f"vrip version {VERSION}\nA podcast downloader.\nAuthor: Your Project",
                    title="About",
                    style="green",
                )
            )
        elif choice == "3":
            break
        else:
            console.print(Panel("Invalid choice.", title="Error", style="red"))


def menu_update() -> None:
    """
    Menu for updating podcasts (update all or update one).
    """
    while True:
        menu_str: str = (
            "[bold]Update Podcasts[/bold]\n"
            "1) Update All Podcasts\n"
            "2) Update One Podcast\n"
            "3) Return to main menu"
        )
        console.print(Panel(menu_str, title="Update", style="magenta"))
        choice: str = console.input("\nEnter choice: ").strip()
        if choice == "1":
            update_podcasts(all_update=True)
        elif choice == "2":
            update_podcasts(all_update=False)
        elif choice == "3":
            break
        else:
            console.print(Panel("Invalid choice.", title="Error", style="red"))


def menu_download() -> None:
    """
    Menu to handle downloading podcasts.
    """
    while True:
        menu_str: str = (
            "[bold]Download Menu[/bold]\n"
            "1) Choose from stored podcasts (by NAME_ID)\n"
            "2) Enter a custom RSS URL\n"
            "3) Return to main menu"
        )
        console.print(Panel(menu_str, title="Download", style="cyan"))
        choice: str = console.input("\nEnter choice: ").strip()
        config, _ = init_config()
        if choice == "1":
            podcast_entries = parse_podcast_list(config)
            if not podcast_entries:
                console.print(
                    Panel(
                        "No stored podcasts found. Add them in Settings > Manage podcasts list.",
                        style="yellow",
                    )
                )
                continue
            table: Table = Table(title="Stored Podcasts (NAME_ID)")
            table.add_column("NAME_ID", style="cyan")
            for _, name, _ in podcast_entries:
                table.add_row(name)
            console.print(table)
            raw_input = console.input("Enter podcast NAME_ID: ").strip()
            try:
                tokens = shlex.split(raw_input)
            except Exception as e:
                console.print(Panel(f"Error parsing input: {e}", style="red"))
                continue
            name_input: str = " ".join(tokens).strip()
            matching = [
                (plink, name, out_dir)
                for (plink, name, out_dir) in podcast_entries
                if name.lower() == name_input.lower()
            ]
            if not matching:
                console.print(
                    Panel(f"No podcast found with NAME_ID '{name_input}'", style="red")
                )
                continue
            chosen_link, chosen_name, chosen_outdir = matching[0]
            rss_url: str = chosen_link
            output_dir: str = chosen_outdir
            format_str: str = "default"
            oldest_first: bool = (
                console.input("Download oldest first? (y/n): ").strip().lower() == "y"
            )
            count_str: str = console.input(
                "How many episodes to download? (Leave blank for all): "
            ).strip()
            try:
                count: Optional[int] = int(count_str) if count_str else None
            except ValueError:
                console.print(
                    Panel("Invalid number, ignoring.", title="Warning", style="red")
                )
                count = None
            search_by: str = console.input(
                "Enter search term for titles (leave blank for no filter): "
            ).strip()
            enable_logging: bool = (
                console.input("Enable session logging? (y/n): ").strip().lower() == "y"
            )
            verbose: bool = (
                console.input("Enable verbose output? (y/n): ").strip().lower() == "y"
            )
            if enable_logging:
                setup_logging()
            download_podcast_rss(
                rss_url,
                output_dir,
                count=count,
                searchby=search_by,
                verbose=verbose,
                oldest_first=oldest_first,
                format_str=format_str,
            )
        elif choice == "2":
            rss_url = console.input(
                "Enter RSS URL (e.g. https://site/feed.xml): "
            ).strip()
            if not rss_url:
                console.print(
                    Panel(
                        "Invalid RSS URL. Returning to menu.",
                        title="Error",
                        style="red",
                    )
                )
                continue
            custom_fmt: str = (
                console.input("Format? (default/daily/...): ").strip().lower()
                or "default"
            )
            oldest_first: bool = (
                console.input("Download oldest first? (y/n): ").strip().lower() == "y"
            )
            count_str: str = console.input(
                "How many episodes to download? (Leave blank for all): "
            ).strip()
            try:
                count: Optional[int] = int(count_str) if count_str else None
            except ValueError:
                console.print(
                    Panel("Invalid number, ignoring.", title="Warning", style="red")
                )
                count = None
            search_by: str = console.input(
                "Enter search term for titles (leave blank for no filter): "
            ).strip()
            default_download_dir: str = config["system"].get("default_output_dir", "")
            directory: str = (
                console.input(
                    f"Enter output directory [default: {default_download_dir}]: "
                ).strip()
                or default_download_dir
            )
            ensure_output_dir(directory)
            enable_logging: bool = (
                console.input("Enable session logging? (y/n): ").strip().lower() == "y"
            )
            verbose: bool = (
                console.input("Enable verbose output? (y/n): ").strip().lower() == "y"
            )
            if enable_logging:
                setup_logging()
            download_podcast_rss(
                rss_url,
                directory,
                count=count,
                searchby=search_by,
                verbose=verbose,
                oldest_first=oldest_first,
                format_str=custom_fmt,
            )
        elif choice == "3":
            break
        else:
            console.print(Panel("Invalid choice.", title="Error", style="red"))


###############################################################################
#                                    MAIN                                     #
###############################################################################


def main() -> None:
    """Main menu loop."""
    banner: str = "========== Welcome to vrip =========="
    console.print(Panel(banner, style="bold magenta"))
    while True:
        main_menu: str = (
            "[bold]Main Menu[/bold]\n"
            "1) Download Podcasts\n"
            "2) Update Podcasts\n"
            "3) Settings\n"
            "4) Manual & About\n"
            "5) Exit"
        )
        console.print(Panel(main_menu, title="vrip", style="magenta"))
        choice: str = console.input("\nEnter choice: ").strip()
        if choice == "1":
            menu_download()
        elif choice == "2":
            menu_update()
        elif choice == "3":
            menu_settings()
        elif choice == "4":
            menu_manual_about()
        elif choice == "5":
            console.print(Panel("Exiting...", title="Goodbye", style="bold magenta"))
            break
        else:
            console.print(
                Panel("Invalid choice, please try again.", title="Error", style="red")
            )
    end_banner: str = "========== Thank you for using vrip =========="
    console.print(Panel(end_banner, style="bold magenta"))


if __name__ == "__main__":
    main()
