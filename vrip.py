#!/usr/bin/env python3

import os
import argparse
import sys
import requests
import feedparser
from rich.console import Console
from rich.progress import (
    Progress,
    BarColumn,
    TextColumn,
    TimeElapsedColumn,
    ProgressColumn,
)
from pytube import YouTube
import subprocess
import logging
from datetime import datetime
import platform
import configparser
import shutil  # For checking if 'choco' exists

console = Console()

# Version variable
VERSION = "1.0.3"

class MBPercentColumn(ProgressColumn):
    """Custom column to show downloaded/total size in MB and percentage."""
    def render(self, task) -> str:
        if task.total is None:
            return "0.00MB/??MB (0%)"

        completed_mb = task.completed / (1024 * 1024)
        total_mb = task.total / (1024 * 1024)
        percentage = (task.completed / task.total) * 100 if task.total else 0
        return f"{completed_mb:>5.2f}MB/{total_mb:>5.2f}MB ({percentage:>5.1f}%)"

def clear_screen():
    """Clear the terminal screen (cls on Windows, clear on Linux)."""
    if os.name == 'nt':
        os.system('cls')
    else:
        os.system('clear')

# Dynamically determine where the config file should live.
def get_config_path():
    """
    Returns the path to the rehab.ini file.
      - On Linux: ~/programs/rehab-ini/rehab.ini
      - On Windows: <script_directory>/rehab.ini
    """
    if os.name == 'nt':
        script_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(script_dir, "rehab.ini")
    else:
        home_dir = os.path.expanduser("~")
        return os.path.join(home_dir, "programs", "rehab-ini", "rehab.ini")

def ensure_output_dir(output_dir):
    """Ensure the output directory exists, creating it if necessary."""
    try:
        os.makedirs(output_dir, exist_ok=True)
    except OSError as e:
        console.print(f"[red]Error:[/red] Unable to create output directory '{output_dir}'. {e}", style="bold red")
        sys.exit(1)

def setup_logging(log_session):
    """Set up logging if --log-session is enabled."""
    if not log_session:
        return None

    # Use the user's home directory in a cross-platform way
    log_dir = os.path.join(os.path.expanduser("~"), "pylogs", "rehab")
    ensure_output_dir(log_dir)

    log_file = os.path.join(log_dir, f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    logging.basicConfig(
        filename=log_file,
        filemode="w",
        format="%(asctime)s - %(levelname)s - %(message)s",
        level=logging.INFO
    )
    console.print(f"[green]Session logs will be saved to:[/green] {log_file}", style="bold green")
    return log_file

def install_dependencies_linux(verbose):
    """Install required dependencies for Linux systems."""
    dependencies = ["ffmpeg", "yt-dlp"]
    command = ["sudo", "apt-get", "install", "-y"] + dependencies

    if verbose:
        console.print(f"[blue]Installing dependencies: {dependencies}[/blue]")
        command.append("--verbose")

    try:
        subprocess.run(command, check=True)
        console.print("[green]Linux dependencies installed successfully![/green]")
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Error installing dependencies:[/red] {e}", style="bold red")

def install_dependencies_windows(verbose):
    """Install required dependencies for Windows systems using Chocolatey."""
    if shutil.which("choco") is None:
        console.print("[red]Chocolatey is not installed. Please install Chocolatey to continue.[/red]", style="bold red")
        return

    dependencies = ["ffmpeg", "yt-dlp"]
    try:
        for dep in dependencies:
            if verbose:
                console.print(f"[blue]Installing dependency: {dep}[/blue]")
            subprocess.run(["choco", "install", dep, "-y"], check=True)
        console.print("[green]Windows dependencies installed successfully![/green]")
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Error installing dependencies:[/red] {e}", style="bold red")

def init_config():
    """
    Creates or loads a rehab.ini config in the OS-specific location:
      - Linux:   ~/programs/rehab-ini/rehab.ini
      - Windows: same directory as the script
    If the file is missing, create with default placeholders.
    """
    config_path = get_config_path()
    config_dir  = os.path.dirname(config_path)

    if not os.path.exists(config_dir):
        os.makedirs(config_dir, exist_ok=True)

    config = configparser.ConfigParser()

    if os.path.exists(config_path):
        config.read(config_path)
        console.print(f"[blue]Loading existing config from: {config_path}[/blue]")
    else:
        console.print(f"[yellow]Config not found. Creating default config at: {config_path}[/yellow]", style="bold yellow")
        config["user"] = {
            "name": "",
            "password": ""
        }
        config["system"] = {
            "os": platform.system().lower()
        }
        with open(config_path, "w") as configfile:
            config.write(configfile)
        console.print("[green]Default rehab.ini created.[/green]", style="bold green")

    return config, config_path

def validate_config():
    """
    Interactive check to ensure the user, password, and system OS are set in rehab.ini.
    If missing, prompt the user to update them.
    """
    config, config_path = init_config()
    changed = False

    if "user" not in config:
        config["user"] = {}
    if "system" not in config:
        config["system"] = {}

    if not config["user"].get("name"):
        console.print("[yellow]No user name found. Let's fix that.[/yellow]", style="bold yellow")
        config["user"]["name"] = console.input("[blue]Enter your name: [/blue]")
        changed = True

    if not config["user"].get("password"):
        console.print("[yellow]No password found. Let's fix that.[/yellow]", style="bold yellow")
        config["user"]["password"] = console.input("[blue]Enter your password: [/blue]")
        changed = True

    if not config["system"].get("os"):
        console.print("[yellow]No OS info found. Let's fix that.[/yellow]", style="bold yellow")
        config["system"]["os"] = console.input("[blue]Enter your OS (linux/windows): [/blue]")
        changed = True

    if changed:
        with open(config_path, "w") as f:
            config.write(f)
        console.print("[green]Configuration updated successfully![/green]")
    else:
        console.print("[green]Configuration is already good to go.[/green]")

def download_with_progress(url, output_path, description="Downloading"):
    """Download a file with a progress bar in MB and %."""
    response = requests.get(url, stream=True)
    total_size = int(response.headers.get('content-length', 0))

    with open(output_path, 'wb') as file, Progress(
            TextColumn("[bold blue]{task.description}[/bold blue] "),
            BarColumn(),
            MBPercentColumn(),
            TimeElapsedColumn(),
    ) as progress:
        task = progress.add_task(description, total=total_size)
        for chunk in response.iter_content(chunk_size=8192):
            file.write(chunk)
            progress.update(task, advance=len(chunk))

    console.print(f"[green]Download complete! Saved at:[/green] {output_path}")

def download_podcast_rss(rss_url, output_dir, count=None, searchby=None, debug=False, verbose=False):
    """Download episodes from a podcast RSS feed."""
    if verbose:
        console.print(f"[blue]Fetching RSS feed from:[/blue] {rss_url}")
        console.print(f"[blue]Output directory:[/blue] {output_dir}")

    ensure_output_dir(output_dir)
    feed = feedparser.parse(rss_url)

    if not feed.entries:
        console.print(f"[yellow]No episodes found in RSS feed:[/yellow] {rss_url}")
        return

    filtered_entries = (
        [entry for entry in feed.entries if searchby.lower() in entry.title.lower()]
        if searchby else feed.entries
    )

    entries_to_download = filtered_entries[:count] if count else filtered_entries

    if not entries_to_download:
        console.print(f"[yellow]No episodes found matching the search term:[/yellow] '{searchby}'")
        return

    for index, entry in enumerate(entries_to_download, start=1):
        title = entry.title
        link = entry.enclosures[0].href if entry.enclosures else None

        if not link:
            console.print(f"[yellow]Skipping episode '{title}' (no downloadable link found).[/yellow]")
            continue

        sanitized_title = "".join(c for c in title if c.isalnum() or c in " _-").rstrip()
        file_path = os.path.join(output_dir, f"{sanitized_title}.mp3")

        if verbose:
            console.print(f"[blue]Downloading podcast episode:[/blue] {title}")
            console.print(f"[blue]  Episode link:[/blue] {link}")
            console.print(f"[blue]  Saving to:[/blue] {file_path}")

        try:
            download_with_progress(link, file_path, description=f"Podcast {index}/{len(entries_to_download)}")
            console.print(f"[green]Saved:[/green] {file_path}")
        except requests.RequestException as e:
            console.print(f"[red]Error downloading episode '{title}':[/red] {e}", style="bold red")

        clear_screen()

def download_youtube_content(url, output_dir, audio_only=False, use_title=False, set_title=None, yt_dlp=False, verbose=False):
    """Download YouTube content using pytube or yt-dlp."""
    ensure_output_dir(output_dir)

    if yt_dlp:
        output_template = (
            os.path.join(output_dir, "%(title)s.%(ext)s")
            if use_title
            else os.path.join(output_dir, f"{set_title or 'Untitled'}.%(ext)s")
        )
        format_option = "bestaudio" if audio_only else "bestvideo+bestaudio"

        try:
            command = [
                "yt-dlp",
                "-f", format_option,
                "--output", output_template,
                url
            ]
            if verbose:
                command.append("--verbose")
            subprocess.run(command, check=True)
            console.print(f"[green]Download completed using yt-dlp.[/green]")
        except subprocess.CalledProcessError as e:
            console.print(f"[red]Error downloading with yt-dlp:[/red] {e}", style="bold red")
    else:
        try:
            yt = YouTube(url)
            title = yt.title if use_title else set_title
            if not title:
                title = "Untitled"

            sanitized_title = "".join(c for c in title if c.isalnum() or c in " _-").rstrip()
            file_extension = "mp3" if audio_only else "mp4"
            file_path = os.path.join(output_dir, f"{sanitized_title}.{file_extension}")

            if verbose:
                console.print(f"[blue]Resolved title:[/blue] {yt.title}")
                console.print(f"[blue]Saving to:[/blue] {file_path}")

            if audio_only:
                stream = yt.streams.filter(only_audio=True).first()
            else:
                stream = yt.streams.get_highest_resolution()

            if not stream:
                console.print(f"[red]Error:[/red] No suitable stream found for the video.")
                return

            with Progress(
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                console=console
            ) as progress:
                task = progress.add_task("Downloading...", total=stream.filesize)
                stream.download(output_path=output_dir, filename=f"{sanitized_title}.{file_extension}")
                progress.update(task, completed=stream.filesize)

            console.print(f"[green]Saved:[/green] {file_path}")
        except Exception as e:
            console.print(f"[red]Error downloading YouTube content:[/red] {e}", style="bold red")

    clear_screen()

def manage_settings_config():
    """Create, edit, or view rehab.ini from the known OS-specific path."""
    config_path = get_config_path()
    config, _ = init_config()
    console.print("[blue]Settings management selected.[/blue]", style="bold blue")

    action = console.input("[yellow]Choose an action (view/edit): [/yellow]").strip().lower()

    if action == "view":
        if os.path.exists(config_path):
            with open(config_path, "r") as configfile:
                console.print(configfile.read(), style="blue")
        else:
            console.print("[red]No config file found![/red]", style="bold red")
    elif action == "edit":
        validate_config()
    else:
        console.print("[red]Invalid action. Please choose 'view' or 'edit'.[/red]", style="bold red")

def handle_setup_command(args):
    """
    The older 'setup' command logic:
      - If --config is passed, go to config management
      - Else if --linux is passed, install linux dependencies
      - Else if --windows is passed, install windows dependencies
      - If neither is specified, auto-detect the OS
    """
    if args.config:
        manage_settings_config()
        return

    current_os = platform.system().lower()
    if args.linux:
        install_dependencies_linux(verbose=args.verbose)
    elif args.windows:
        install_dependencies_windows(verbose=args.verbose)
    else:
        console.print(f"[yellow]No OS option provided. Auto-detecting OS: {current_os}[/yellow]")
        if "linux" in current_os:
            install_dependencies_linux(verbose=args.verbose)
        elif "windows" in current_os:
            install_dependencies_windows(verbose=args.verbose)
        else:
            console.print("[red]OS detection failed or unsupported OS. Please specify --linux or --windows.[/red]")

def handle_init_command(args):
    """
    1. Auto-detect OS (Windows or Linux).
    2. Install the appropriate dependencies.
    3. Create or load rehab.ini in the right location.
    4. Prompt user to fill missing details if needed.
    """
    current_os = platform.system().lower()
    console.print(f"[blue]Running 'init' command for OS = {current_os}[/blue]")

    if "windows" in current_os:
        install_dependencies_windows(verbose=args.verbose)
    elif "linux" in current_os:
        install_dependencies_linux(verbose=args.verbose)
    else:
        console.print("[red]Unsupported OS detected. Abort.[/red]")
        return

    config, config_path = init_config()
    validate_config()
    console.print("[green]Initialization complete![/green]")

def handle_man_command():
    """
    Display a thorough manual (man page) explaining how to use the Rehab script.
    """
    manual_text = f"""
[bold cyan]NAME[/bold cyan]
    rehab - A command-line tool to download audio files (podcasts, YouTube) and manage basic app settings.

[bold cyan]SYNOPSIS[/bold cyan]
    rehab [command] [options]

[bold cyan]DESCRIPTION[/bold cyan]
    Rehab is a Python command-line utility designed to simplify the process of downloading audio
    from various sources, such as podcast RSS feeds or YouTube videos. It can also manage its
    own configuration settings and install dependencies required to run the tool.

[bold cyan]COMMANDS[/bold cyan]

    1. [bold]init[/bold]
       Automatically detect your OS (Windows or Linux), install dependencies (ffmpeg, yt-dlp, etc.),
       and create/load the rehab.ini config file. Then interactively prompt for missing details.

       Example usage:
         rehab init

    2. [bold]download[/bold]
       Download audio from a podcast RSS feed and/or YouTube.

       Options for [bold]download[/bold]:
         - [italic]-d, --dir[/italic]
             Specify the base output directory for downloads.
             Default: {os.path.join(os.path.expanduser("~"), "Desktop", "Audio")}

         - [italic]--rss[/italic]
             Provide an RSS feed URL (e.g., https://site/feed.xml).
         - [italic]--count[/italic]
             Number of recent podcast episodes to download.
         - [italic]--search-by[/italic]
             Filter podcast episodes by title.
         - [italic]--youtube[/italic]
             Provide a YouTube video URL to download.
         - [italic]--set-title[/italic]
             Set a custom title for the downloaded YouTube content.
         - [italic]--use-title[/italic]
             Use the official YouTube video title for the filename.
         - [italic]--audio-only[/italic]
             Download only the audio from YouTube (mp3).
         - [italic]--yt-dlp[/italic]
             Use yt-dlp instead of pytube for YouTube.
         - [italic]--log-session[/italic]
             Enable session logging.
         - [italic]--verbose[/italic]
             Show extra debug messages.
         - [italic]--version[/italic]
             Display the script version and exit.

       Example usage:
         rehab download --rss https://example.com/podcast/feed.xml --count 5
         rehab download --youtube https://youtube.com/watch?v=abc --audio-only --use-title

    3. [bold]setup[/bold]
       Manually install dependencies or manage config.
         - [italic]--linux[/italic] or [italic]--windows[/italic]
         - [italic]--config[/italic]
         - [italic]--verbose[/italic]

       Examples:
         rehab setup --linux
         rehab setup --config
         rehab setup --windows

    4. [bold]man[/bold]
       Display this manual.

[bold cyan]CONFIGURATION[/bold cyan]
    Rehab uses a "rehab.ini" file in:
        - Linux:   ~/programs/rehab-ini/rehab.ini
        - Windows: Same directory as the script

[bold cyan]VERSION[/bold cyan]
    {VERSION}

[bold cyan]AUTHOR[/bold cyan]
    This script is maintained by [Your Project/Name].

[bold cyan]COPYRIGHT[/bold cyan]
    Distributed under the MIT License.
"""
    console.print(manual_text, style="white")

def main():
    parser = argparse.ArgumentParser(description="Rehab: download audio", add_help=True)
    subparsers = parser.add_subparsers(dest="command", required=True)

    # init command
    init_parser = subparsers.add_parser("init", help="Auto-detect OS, install dependencies, and set up rehab.ini.")
    init_parser.add_argument("--verbose", action="store_true", help="Show additional debugging information.")

    # download command
    download_parser = subparsers.add_parser("download", help="Download audio from a podcast RSS feed or YouTube.")
    download_parser.add_argument("-d", "--dir", default=os.path.join(os.path.expanduser("~"), "Desktop", "Audio"),
        help="Base output directory for downloads.")
    download_parser.add_argument("--rss", help="Podcast RSS feed (e.g., https://site/feed.xml).")
    download_parser.add_argument("--count", type=int, help="Number of most recent RSS episodes to download.")
    download_parser.add_argument("--search-by", help="String to search for in podcast titles.")
    download_parser.add_argument("--youtube", help="Download content from a YouTube URL.")
    download_parser.add_argument("--set-title", help="Set a custom title for the downloaded YouTube content.")
    download_parser.add_argument("--use-title", action="store_true", help="Use the YouTube video's title for the filename.")
    download_parser.add_argument("--audio-only", action="store_true", help="Download only the audio (mp3).")
    download_parser.add_argument("--yt-dlp", action="store_true", help="Use yt-dlp instead of pytube for YouTube.")
    download_parser.add_argument("--log-session", action="store_true", help="Log the session in ~/pylogs/rehab.")
    download_parser.add_argument("--verbose", action="store_true", help="Show additional debugging information.")
    download_parser.add_argument("--version", action="store_true", help="Display the current version of the script.")

    # setup command
    setup_parser = subparsers.add_parser("setup", help="Manually install dependencies or manage config.")
    setup_parser.add_argument("--linux", action="store_true", help="Install dependencies for Linux.")
    setup_parser.add_argument("--windows", action="store_true", help="Install dependencies for Windows.")
    setup_parser.add_argument("--config", action="store_true", help="Create, edit, or view rehab.ini.")
    setup_parser.add_argument("--verbose", action="store_true", help="Show additional debug messages.")

    # man command
    man_parser = subparsers.add_parser("man", help="Display a thorough manual for the Rehab tool.")

    args = parser.parse_args()

    if args.command == "init":
        handle_init_command(args)
    elif args.command == "setup":
        handle_setup_command(args)
    elif args.command == "download":
        if args.log_session:
            setup_logging(args.log_session)
        if args.version:
            console.print(f"[green]Version: {VERSION}[/green]")
            sys.exit(0)
        if args.rss:
            download_podcast_rss(
                rss_url=args.rss,
                output_dir=args.dir,
                count=args.count,
                searchby=args.search_by,
                debug=args.verbose,
                verbose=args.verbose
            )
        if args.youtube:
            download_youtube_content(
                url=args.youtube,
                output_dir=args.dir,
                audio_only=args.audio_only,
                use_title=args.use_title,
                set_title=args.set_title,
                yt_dlp=args.yt_dlp,
                verbose=args.verbose
            )
    elif args.command == "man":
        handle_man_command()

if __name__ == "__main__":
    main()
