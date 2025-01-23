#!/home/sohfix/PycharmProjects/rehab/renv/bin/python3

import os
import argparse
import sys
import requests
import feedparser
from rich.console import Console
from rich.progress import Progress, BarColumn, TextColumn
from pytube import YouTube
import subprocess
import logging
from datetime import datetime
import platform
import configparser

console = Console()


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
        console.print("[green]Settings file updated successfully![/green]", style="bold green")
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


def setup_dependencies(os_type, verbose=False):
    """Install dependencies based on the operating system."""
    dependencies_installed = False

    try:
        if os_type == "linux":
            if verbose:
                console.print("[blue]Installing dependencies for Linux...[/blue]")
            subprocess.run(["sudo", "apt-get", "update"], check=True)
            subprocess.run(["sudo", "apt-get", "install", "-y", "python3-pip", "ffmpeg"], check=True)
            dependencies_installed = True

        elif os_type == "windows":
            if verbose:
                console.print("[blue]Installing dependencies for Windows...[/blue]")
            subprocess.run(["choco", "install", "ffmpeg", "-y"], check=True)
            dependencies_installed = True

        else:
            console.print("[red]Unsupported OS type provided.[/red]", style="bold red")
            return False

        if dependencies_installed:
            console.print("[green]Running 'sudo apt autoremove'.[/green]", style="bold green")
            password = get_password_from_config()
            subprocess.run(["sudo", "-S", "apt", "autoremove"], input=f"{password}\n", text=True, check=True)

    except subprocess.CalledProcessError as e:
        console.print(f"[red]Error during installation:[/red] {e}", style="bold red")
        log_message(f"Error during dependency installation: {e}")
        return False

    return dependencies_installed


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
    download_parser.add_argument("--audio-only", action="store_true", help="Download only audio as MP3.")
    download_parser.add_argument("--use-title", action="store_true", help="Use the YouTube video's title.")
    download_parser.add_argument("--set-title", help="Set a custom title for the downloaded YouTube content.")
    download_parser.add_argument("--yt-dlp", action="store_true",
                                 help="Use yt-dlp instead of pytube for downloading YouTube content.")
    download_parser.add_argument("--log-session", action="store_true", help="Log the session in '$HOME/pylogs/rehab'.")
    download_parser.add_argument("--verbose", action="store_true",
                                 help="Show additional messages explaining each step.")

    # Setup Command
    setup_parser = subparsers.add_parser("setup", help="Installs dependencies for rehab.")
    setup_parser.add_argument("--linux", action="store_true", help="Install dependencies for Linux.")
    setup_parser.add_argument("--windows", action="store_true", help="Install dependencies for Windows.")
    setup_parser.add_argument("--ini", action="store_true",
                              help="Walkthrough to edit or validate the settings.ini file.")
    setup_parser.add_argument("--verbose", action="store_true", help="Show additional messages explaining each step.")
    setup_parser.add_argument("--log-session", action="store_true", help="Log the session in '$HOME/pylogs/rehab'.")

    args = parser.parse_args()

    # Set up logging if requested
    log_file = setup_logging(args.log_session)

    if args.command == "setup":
        if args.ini:
            config_path = setup_config()
            validate_and_edit_config(config_path)
            console.print("[green]INI file setup and validated successfully![/green]", style="bold green")

        if args.linux:
            success = setup_dependencies("linux", verbose=args.verbose)
        elif args.windows:
            success = setup_dependencies("windows", verbose=args.verbose)
        else:
            console.print("[yellow]Please specify an OS using --linux or --windows.[/yellow]", style="bold yellow")
            sys.exit(1)

        if success:
            console.print("[green]All dependencies are set up and ready to go![/green]", style="bold green")
            log_message("Setup complete.")
        else:
            console.print("[red]Setup encountered errors. Check the logs for more details.[/red]", style="bold red")
            log_message("Setup encountered errors.")


if __name__ == "__main__":
    main()
