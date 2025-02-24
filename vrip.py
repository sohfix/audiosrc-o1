#!/home/sohfix/PycharmProjects/audiosrc/audiosrc-env/bin/python3.13

@AUTHOR_EMAIL = 'sohfix'
import os
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
from rich.panel import Panel
from pytube import YouTube
import subprocess
import logging
from datetime import datetime
import platform
import configparser
import shutil

console = Console()

VERSION = "01.01.3 [ruv]"


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
    """Clear the terminal screen using Rich."""
    console.clear()


def get_config_path():
    """
    Returns the path to the vrip.ini file:
      - On Linux:   ~/programs/vrip-ini/vrip.ini
      - On Windows: same directory as the script
    """
    if os.name == 'nt':
        script_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(script_dir, "vrip.ini")
    else:
        home_dir = os.path.expanduser("~")
        return os.path.join(home_dir, "programs", "vrip-ini", "vrip.ini")


def ensure_output_dir(output_dir):
    """Ensure the output directory exists, creating it if necessary."""
    try:
        os.makedirs(output_dir, exist_ok=True)
    except OSError as e:
        console.print(Panel(f"Error: Unable to create output directory '{output_dir}'.\n{e}",
                              title="Error", style="red"))
        sys.exit(1)


def setup_logging():
    """Enable session logging."""
    log_dir = os.path.join(os.path.expanduser("~"), "pylogs", "vrip")
    ensure_output_dir(log_dir)
    log_file = os.path.join(log_dir, f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    logging.basicConfig(
        filename=log_file,
        filemode="w",
        format="%(asctime)s - %(levelname)s - %(message)s",
        level=logging.INFO
    )
    console.print(Panel(f"Session logs will be saved to:\n{log_file}", title="Logging", style="green"))


def install_dependencies_linux(verbose):
    """Install required dependencies for Linux systems."""
    dependencies = ["ffmpeg", "yt-dlp"]
    command = ["sudo", "apt-get", "install", "-y"] + dependencies

    if verbose:
        console.print(Panel(f"Installing dependencies:\n{dependencies}",
                              title="Linux Dependencies", style="blue"))
        command.append("--verbose")

    try:
        subprocess.run(command, check=True)
        console.print(Panel("Linux dependencies installed successfully!",
                            title="Success", style="green"))
    except subprocess.CalledProcessError as e:
        console.print(Panel(f"Error installing dependencies:\n{e}",
                            title="Error", style="red"))


def install_dependencies_windows(verbose):
    """Install required dependencies for Windows systems using Chocolatey."""
    if shutil.which("choco") is None:
        console.print(Panel("Chocolatey is not installed. Please install Chocolatey to continue.",
                            title="Error", style="red"))
        return

    dependencies = ["ffmpeg", "yt-dlp"]
    try:
        for dep in dependencies:
            if verbose:
                console.print(Panel(f"Installing dependency: {dep}",
                                      title="Windows Dependencies", style="blue"))
            subprocess.run(["choco", "install", dep, "-y"], check=True)
        console.print(Panel("Windows dependencies installed successfully!",
                            title="Success", style="green"))
    except subprocess.CalledProcessError as e:
        console.print(Panel(f"Error installing dependencies:\n{e}",
                            title="Error", style="red"))


def init_config():
    """
    Creates or loads a vrip.ini config in the OS-specific location.
      - Linux:   ~/programs/vrip-ini/vrip.ini
      - Windows: same directory as the script
    """
    config_path = get_config_path()
    config_dir = os.path.dirname(config_path)

    if not os.path.exists(config_dir):
        os.makedirs(config_dir, exist_ok=True)

    config = configparser.ConfigParser()

    if os.path.exists(config_path):
        config.read(config_path)
        console.print(Panel(f"Loading existing config from:\n{config_path}",
                            title="Config", style="blue"))
    else:
        console.print(Panel(f"Config not found. Creating default config at:\n{config_path}",
                            title="Config", style="yellow"))
        config["user"] = {"name": "", "password": ""}
        config["system"] = {"os": platform.system().lower()}
        with open(config_path, "w") as configfile:
            config.write(configfile)
        console.print(Panel("Default vrip.ini created.", title="Config", style="green"))

    return config, config_path


def validate_config():
    """
    Interactive check to ensure that the user name, password, and system OS are set in vrip.ini.
    """
    config, config_path = init_config()
    changed = False

    if "user" not in config:
        config["user"] = {}
    if "system" not in config:
        config["system"] = {}

    if not config["user"].get("name"):
        console.print(Panel("No user name found. Let's fix that.",
                            title="Config Update", style="yellow"))
        config["user"]["name"] = console.input("[blue]Enter your name: [/blue]")
        changed = True

    if not config["user"].get("password"):
        console.print(Panel("No password found. Let's fix that.",
                            title="Config Update", style="yellow"))
        config["user"]["password"] = console.input("[blue]Enter your password: [/blue]")
        changed = True

    if not config["system"].get("os"):
        console.print(Panel("No OS info found. Let's fix that.",
                            title="Config Update", style="yellow"))
        config["system"]["os"] = console.input("[blue]Enter your OS (linux/windows): [/blue]")
        changed = True

    if changed:
        with open(config_path, "w") as f:
            config.write(f)
        console.print(Panel("Configuration updated successfully!",
                            title="Config", style="green"))
    else:
        console.print(Panel("Configuration is already good to go.",
                            title="Config", style="green"))


def download_with_progress(url, output_path, description="Downloading"):
    """Download a file with a progress bar showing MB and percentage."""
    response = requests.get(url, stream=True)
    total_size = int(response.headers.get('content-length', 0))

    with open(output_path, 'wb') as file, Progress(
            TextColumn("[bold blue]{task.description}[/bold blue]"),
            BarColumn(),
            MBPercentColumn(),
            TimeElapsedColumn(),
            console=console,
    ) as progress:
        task = progress.add_task(description, total=total_size)
        for chunk in response.iter_content(chunk_size=8192):
            file.write(chunk)
            progress.update(task, advance=len(chunk))

    console.print(Panel(f"Download complete! Saved at:\n{output_path}",
                        title="Download", style="green"))


def download_podcast_rss(rss_url, output_dir, count=None, searchby=None, verbose=False):
    """Download episodes from a podcast RSS feed."""
    if verbose:
        console.print(Panel(f"Fetching RSS feed from:\n{rss_url}\nOutput directory:\n{output_dir}",
                            title="Podcast RSS", style="blue"))
    ensure_output_dir(output_dir)
    feed = feedparser.parse(rss_url)

    if not feed.entries:
        console.print(Panel(f"No episodes found in RSS feed:\n{rss_url}",
                            title="Podcast RSS", style="yellow"))
        return

    filtered_entries = (
        [entry for entry in feed.entries if searchby.lower() in entry.title.lower()]
        if searchby else feed.entries
    )
    entries_to_download = filtered_entries[:count] if count else filtered_entries

    if not entries_to_download:
        console.print(Panel(f"No episodes found matching the search term:\n'{searchby}'",
                            title="Podcast RSS", style="yellow"))
        return

    for index, entry in enumerate(entries_to_download, start=1):
        title = entry.title
        link = entry.enclosures[0].href if entry.enclosures else None

        if not link:
            console.print(Panel(f"Skipping episode '{title}' (no downloadable link found).",
                                title="Podcast RSS", style="yellow"))
            continue

        sanitized_title = "".join(c for c in title if c.isalnum() or c in " _-").rstrip()
        file_path = os.path.join(output_dir, f"{sanitized_title}.mp3")

        if verbose:
            console.print(Panel(f"Downloading podcast episode:\n{title}\nEpisode link:\n{link}\nSaving to:\n{file_path}",
                                title="Podcast RSS", style="blue"))

        try:
            download_with_progress(link, file_path, description=f"Podcast {index}/{len(entries_to_download)}")
            console.print(Panel(f"Saved:\n{file_path}", title="Podcast RSS", style="green"))
        except requests.RequestException as e:
            console.print(Panel(f"Error downloading episode '{title}': {e}",
                                title="Error", style="red"))

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
            console.print(Panel("Download completed using yt-dlp.",
                                title="YouTube", style="green"))
        except subprocess.CalledProcessError as e:
            console.print(Panel(f"Error downloading with yt-dlp:\n{e}",
                                title="Error", style="red"))
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
                console.print(Panel(f"Resolved title:\n{yt.title}\nSaving to:\n{file_path}",
                                    title="YouTube", style="blue"))

            stream = yt.streams.filter(only_audio=True).first() if audio_only else yt.streams.get_highest_resolution()
            if not stream:
                console.print(Panel("Error: No suitable stream found for the video.",
                                    title="Error", style="red"))
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

            console.print(Panel(f"Saved:\n{file_path}", title="YouTube", style="green"))
        except Exception as e:
            console.print(Panel(f"Error downloading YouTube content:\n{e}",
                                title="Error", style="red"))

    clear_screen()


def manage_settings_config():
    """Create, edit, or view vrip.ini from the known OS-specific path."""
    config_path = get_config_path()
    config, _ = init_config()
    console.print(Panel("Settings management selected.", title="Settings", style="blue"))

    action = console.input("[yellow]Choose an action (view/edit): [/yellow]").strip().lower()

    if action == "view":
        if os.path.exists(config_path):
            with open(config_path, "r") as configfile:
                console.print(Panel(configfile.read(), title="vrip.ini", style="blue"))
        else:
            console.print(Panel("No config file found!", title="Error", style="red"))
    elif action == "edit":
        validate_config()
    else:
        console.print(Panel("Invalid action. Please choose 'view' or 'edit'.",
                            title="Error", style="red"))


def handle_setup_command():
    """Display the setup menu for managing configuration or installing dependencies."""
    menu_text = (
        "[bold]Setup Menu[/bold]\n"
        "1) Manage config (create/edit/view vrip.ini)\n"
        "2) Install dependencies (Linux)\n"
        "3) Install dependencies (Windows)\n"
        "4) Auto-detect and install dependencies\n"
        "5) Return to main menu"
    )
    console.print(Panel(menu_text, title="Setup", style="cyan"))
    choice = console.input("\nEnter choice: ").strip()

    if choice == "1":
        manage_settings_config()
    elif choice == "2":
        install_dependencies_linux(verbose=True)
    elif choice == "3":
        install_dependencies_windows(verbose=True)
    elif choice == "4":
        current_os = platform.system().lower()
        console.print(Panel(f"Auto-detected OS: {current_os}",
                            title="Auto-detect", style="yellow"))
        if "linux" in current_os:
            install_dependencies_linux(verbose=True)
        elif "windows" in current_os:
            install_dependencies_windows(verbose=True)
        else:
            console.print(Panel("Unsupported OS or detection failed.",
                                title="Error", style="red"))
    elif choice == "5":
        return
    else:
        console.print(Panel("Invalid choice.", title="Error", style="red"))


def handle_init_command():
    """
    Auto-detect OS, install the appropriate dependencies,
    create or load vrip.ini, and prompt for missing details.
    """
    current_os = platform.system().lower()
    console.print(Panel(f"Running 'init' command for OS = {current_os}",
                        title="Init", style="blue"))

    if "windows" in current_os:
        install_dependencies_windows(verbose=True)
    elif "linux" in current_os:
        install_dependencies_linux(verbose=True)
    else:
        console.print(Panel("Unsupported OS detected. Abort.",
                            title="Error", style="red"))
        return

    init_config()
    validate_config()
    console.print(Panel("Initialization complete!", title="Init", style="green"))


def handle_man_command():
    """Display a thorough manual explaining how to use the vrip script."""
    manual_text = f"""
[bold cyan]NAME[/bold cyan]
    vrip (Menu Version) - A command-line tool for downloading audio files (podcasts, YouTube) and managing basic app settings.

[bold cyan]DESCRIPTION[/bold cyan]
    A menu-driven version of vrip simplifies downloading audio from sources like podcast RSS feeds or YouTube videos.
    It also manages its configuration settings and installs dependencies.

[bold cyan]MENU OPTIONS[/bold cyan]
    1) init - Auto-detect OS, install dependencies, and configure vrip.ini.
    2) setup - Manually install dependencies or manage vrip.ini.
    3) download - Download audio from podcast RSS feeds or YouTube.
    4) man - Display this manual.
    5) exit - Quit the tool.

[bold cyan]CONFIGURATION[/bold cyan]
    vrip uses a "vrip.ini" file:
      - Linux:   ~/programs/vrip-ini/vrip.ini
      - Windows: Same directory as the script

[bold cyan]VERSION[/bold cyan]
    {VERSION}

[bold cyan]AUTHOR[/bold cyan]
    Maintained by [Your Project/Name].

[bold cyan]COPYRIGHT[/bold cyan]
    Distributed under the MIT License.
"""
    console.print(Panel(manual_text, title="Manual", style="white"))


def handle_download_command():
    """Present a menu to choose podcast or YouTube download options."""
    download_menu = (
        "[bold]Download Menu[/bold]\n"
        "1) Download from podcast RSS\n"
        "2) Download from YouTube\n"
        "3) Return to main menu"
    )
    console.print(Panel(download_menu, title="Download", style="cyan"))
    choice = console.input("\nEnter choice: ").strip()

    # Default download directory
    default_download_dir = os.path.join(os.path.expanduser("~"), "Desktop", "Audio")

    if choice == "1":
        rss_url = console.input("Enter RSS URL (e.g. https://site/feed.xml): ").strip()
        if not rss_url:
            console.print(Panel("Invalid RSS URL. Returning to menu.",
                                title="Error", style="red"))
            return
        count_str = console.input("How many recent episodes to download? (Leave blank for all): ").strip()
        try:
            count = int(count_str) if count_str else None
        except ValueError:
            console.print(Panel("Invalid number, ignoring.",
                                title="Warning", style="red"))
            count = None

        search_by = console.input("Enter search term for titles (leave blank for no filter): ").strip()
        directory = console.input(f"Enter output directory [default: {default_download_dir}]: ").strip() or default_download_dir
        ensure_output_dir(directory)

        enable_logging = console.input("Enable session logging? (y/n): ").strip().lower() == 'y'
        verbose = console.input("Enable verbose output? (y/n): ").strip().lower() == 'y'
        if enable_logging:
            setup_logging()

        download_podcast_rss(rss_url, directory, count=count, searchby=search_by, verbose=verbose)

    elif choice == "2":
        url = console.input("Enter YouTube video URL: ").strip()
        if not url:
            console.print(Panel("Invalid YouTube URL. Returning to menu.",
                                title="Error", style="red"))
            return

        audio_only = console.input("Download audio only? (y/n): ").strip().lower() == 'y'
        use_title  = console.input("Use the YouTube title for the filename? (y/n): ").strip().lower() == 'y'
        set_title  = None
        if not use_title:
            set_title = console.input("Enter custom title (leave blank for 'Untitled'): ").strip() or None

        use_yt_dlp = console.input("Use yt-dlp instead of pytube? (y/n): ").strip().lower() == 'y'
        directory = console.input(f"Enter output directory [default: {default_download_dir}]: ").strip() or default_download_dir
        ensure_output_dir(directory)

        enable_logging = console.input("Enable session logging? (y/n): ").strip().lower() == 'y'
        verbose = console.input("Enable verbose output? (y/n): ").strip().lower() == 'y'
        if enable_logging:
            setup_logging()

        download_youtube_content(
            url=url,
            output_dir=directory,
            audio_only=audio_only,
            use_title=use_title,
            set_title=set_title,
            yt_dlp=use_yt_dlp,
            verbose=verbose
        )

    elif choice == "3":
        return
    else:
        console.print(Panel("Invalid choice.", title="Error", style="red"))


def main():
    """Main menu loop."""
    while True:
        main_menu = (
            "[bold]Main Menu[/bold]\n"
            "1) init (auto-detect OS, install deps, configure vrip.ini)\n"
            "2) setup (manual config or dep install)\n"
            "3) download (RSS or YouTube)\n"
            "4) man (help/manual)\n"
            "5) exit"
        )
        console.print(Panel(main_menu, title="vrip", style="magenta"))
        choice = console.input("\nEnter choice: ").strip()

        if choice == "1":
            handle_init_command()
        elif choice == "2":
            handle_setup_command()
        elif choice == "3":
            handle_download_command()
        elif choice == "4":
            handle_man_command()
        elif choice == "5":
            console.print(Panel("Exiting...", title="Goodbye", style="bold magenta"))
            break
        else:
            console.print(Panel("Invalid choice, please try again.",
                                title="Error", style="red"))


if __name__ == "__main__":
    main()
