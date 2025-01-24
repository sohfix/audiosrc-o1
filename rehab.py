#!/home/sohfix/PycharmProjects/rehab/renv/bin/python3

import os
import argparse
import sys
import requests
import feedparser
from rich.console import Console
from rich.progress import Progress, BarColumn, TextColumn, TimeElapsedColumn
from pytube import YouTube
import subprocess
import logging
from datetime import datetime
import platform
import configparser

console = Console()

# Version variable
VERSION = "1.0.3"

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

    log_dir = os.path.expandvars("$HOME/pylogs/rehab")
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

def log_message(message):
    """Log a message if logging is enabled."""
    if logging.getLogger().hasHandlers():
        logging.info(message)

def setup_config():
    """Create a settings.ini file for the first time if it doesn't exist."""
    config_dir = os.path.expandvars("$HOME/rehab-settings")
    ensure_output_dir(config_dir)
    config_path = os.path.join(config_dir, "settings.ini")

    if not os.path.exists(config_path):
        console.print("[yellow]Settings file not found. Creating a new one...[/yellow]", style="bold yellow")
        config = configparser.ConfigParser()
        config['user'] = {'name': '', 'password': ''}
        config['system'] = {'os': ''}

        with open(config_path, 'w') as configfile:
            config.write(configfile)

        console.print("[green]Settings file created at:[/green]", style="bold green")
        console.print(config_path)
        console.print("[blue]Please edit the file to include your details.[/blue]", style="bold blue")

    return config_path

def validate_and_edit_config(config_path):
    """Validate and edit the settings.ini file through a walkthrough."""
    config = configparser.ConfigParser()
    config.read(config_path)

    changed = False

    if 'user' not in config or 'password' not in config['user'] or not config['user']['password']:
        console.print("[yellow]Password is missing in settings.ini. Let's fix it.[/yellow]", style="bold yellow")
        config['user']['password'] = console.input("[blue]Enter your password: [/blue]")
        changed = True

    if 'user' not in config or 'name' not in config['user'] or not config['user']['name']:
        console.print("[yellow]Name is missing in settings.ini. Let's fix it.[/yellow]", style="bold yellow")
        config['user']['name'] = console.input("[blue]Enter your name: [/blue]")
        changed = True

    if 'system' not in config or 'os' not in config['system'] or not config['system']['os']:
        console.print("[yellow]OS is missing in settings.ini. Let's fix it.[/yellow]", style="bold yellow")
        config['system']['os'] = console.input("[blue]Enter your operating system (linux/windows): [/blue]")
        changed = True

    if changed:
        with open(config_path, 'w') as configfile:
            config.write(configfile)
        console.print("[green]Settings file updated successfully![green]", style="bold green")
    else:
        console.print("[green]Settings file is already properly configured.[/green]", style="bold green")

def get_password_from_config():
    """Retrieve the user's password from the settings.ini file."""
    config_dir = os.path.expandvars("$HOME/rehab-settings")
    config_path = os.path.join(config_dir, "settings.ini")

    if not os.path.exists(config_path):
        setup_config()
        console.print("[yellow]Please fill out the settings.ini file and rerun the setup.[/yellow]",
                      style="bold yellow")
        sys.exit(1)

    validate_and_edit_config(config_path)

    config = configparser.ConfigParser()
    config.read(config_path)

    try:
        password = config['user']['password']
        if not password:
            raise KeyError("Password not set in settings.ini.")
        return password
    except KeyError as e:
        console.print(f"[red]Error in settings.ini:[/red] {e}", style="bold red")
        sys.exit(1)

def download_with_progress(url, output_path, description="Downloading"):
    """Download a file with a progress bar."""
    response = requests.get(url, stream=True)
    total_size = int(response.headers.get('content-length', 0))

    with open(output_path, 'wb') as file, Progress(
        TextColumn("[bold blue]{task.description}[/bold blue]"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total} bytes"),
        TimeElapsedColumn(),
    ) as progress:
        task = progress.add_task(description, total=total_size)

        for chunk in response.iter_content(chunk_size=1024):
            file.write(chunk)
            progress.update(task, advance=len(chunk))

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

    for entry in entries_to_download:
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
            download_with_progress(link, file_path, description="Downloading Podcast")
            console.print(f"[green]Saved:[/green] {file_path}")
        except requests.RequestException as e:
            console.print(f"[red]Error downloading episode '{title}':[/red] {e}", style="bold red")

def download_youtube_content(url, output_dir, audio_only=False, use_title=False, set_title=None, yt_dlp=False, verbose=False):
    """Download YouTube content using pytube or yt-dlp."""
    ensure_output_dir(output_dir)

    if yt_dlp:
        output_template = os.path.join(output_dir, "%(title)s.%(ext)s") if use_title else os.path.join(output_dir, f"{set_title or 'Untitled'}.%(ext)s")
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
                console.print(f"[blue]Resolved title:[/blue] {title}")
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

def manage_settings_config():
    """Provide the ability to create, edit, or use the settings.ini file."""
    config_path = setup_config()

    console.print("[blue]Settings management selected.[/blue]", style="bold blue")
    action = console.input("[yellow]Choose an action (view/edit): [/yellow]").strip().lower()

    if action == "view":
        with open(config_path, "r") as configfile:
            console.print(configfile.read(), style="blue")
    elif action == "edit":
        validate_and_edit_config(config_path)
    else:
        console.print("[red]Invalid action. Please choose 'view' or 'edit'.[/red]", style="bold red")

def main():
    parser = argparse.ArgumentParser(description="Rehab: download audio", add_help=True)
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Download Command
    download_parser = subparsers.add_parser("download",
                                            help="Download audio as MP3 from a URL, text file, or RSS feed.")
    download_parser.add_argument("-d", "--dir", default=os.path.expandvars("$HOME/Desktop/Audio"),
                                 help="Base output directory for downloads.")
    download_parser.add_argument("--rss",
                                 help="Download audio files from a podcast RSS feed (e.g., https://site/feed.xml).")
    download_parser.add_argument("--count", type=int, help="Number of most recent episodes to download.")
    download_parser.add_argument("--search-by", help="String to search for in podcast titles.")
    download_parser.add_argument("--youtube", help="Download content from a YouTube URL.")
    download_parser.add_argument("--set-title", help="Set a custom title for the downloaded YouTube content.")
    download_parser.add_argument("--use-title", action="store_true", help="Use the YouTube video's title.")
    download_parser.add_argument("--audio-only", action="store_true", help="Download only audio as MP3.")
    download_parser.add_argument("--yt-dlp", action="store_true", help="Use yt-dlp instead of pytube for downloading YouTube content.")
    download_parser.add_argument("--log-session", action="store_true", help="Log the session in '$HOME/pylogs/rehab'.")
    download_parser.add_argument("--verbose", action="store_true",
                                 help="Show additional messages explaining each step.")
    download_parser.add_argument("--version", action="store_true", help="Display the current version of the script.")

    # Setup Command
    setup_parser = subparsers.add_parser("setup", help="Installs dependencies for rehab.")
    setup_parser.add_argument("--linux", action="store_true", help="Install dependencies for Linux.")
    setup_parser.add_argument("--windows", action="store_true", help="Install dependencies for Windows.")
    setup_parser.add_argument("--verbose", action="store_true", help="Show additional messages explaining each step.")
    setup_parser.add_argument("--log-session", action="store_true", help="Log the session in '$HOME/pylogs/rehab'.")
    setup_parser.add_argument("--config", action="store_true", help="Create, edit, or view the settings.ini file.")

    args = parser.parse_args()

    # Check version flag
    if getattr(args, "version", False):
        console.print(f"[blue]Rehab Version:[/blue] {VERSION}")
        sys.exit(0)

    # Set up logging if requested
    log_file = setup_logging(args.log_session)

    success = None  # Initialize success variable

    if args.command == "setup":
        if args.config:
            manage_settings_config()
        elif args.linux:
            success = setup_dependencies("linux", verbose=args.verbose)
        elif args.windows:
            success = setup_dependencies("windows", verbose=args.verbose)
        else:
            console.print("[yellow]Please specify an OS using --linux or --windows.[/yellow]", style="bold yellow")
            sys.exit(1)

        if success is not None and success:
            console.print("[green]All dependencies are set up and ready to go![green]", style="bold green")
            log_message("Setup complete.")
        elif success is not None:
            console.print("[red]Setup encountered errors. Check the logs for more details.[/red]", style="bold red")
            log_message("Setup encountered errors.")

    if args.command == "download":
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

if __name__ == "__main__":
    main()
