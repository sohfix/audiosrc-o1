#OPTIMIZED FOR WINDOWS
import os
import sys
import platform
import configparser
import logging
import requests
import feedparser
from datetime import datetime
from rich.console import Console
from rich.progress import (
    Progress,
    BarColumn,
    TextColumn,
    TimeElapsedColumn,
    ProgressColumn,
)
from rich.panel import Panel

console = Console()
VERSION = "01.02.0 [rss-only]"


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
      - On Windows: C:\\vrip_tools\\vrip.ini
      - On Linux:   ~/programs/vrip-ini/vrip.ini
    """
    current_os = platform.system().lower()
    if "windows" in current_os:
        return r"C:\vrip_tools\vrip.ini"
    else:
        home_dir = os.path.expanduser("~")
        return os.path.join(home_dir, "programs", "vrip-ini", "vrip.ini")


def ensure_output_dir(output_dir):
    """Ensure the output directory exists, creating it if necessary."""
    try:
        os.makedirs(output_dir, exist_ok=True)
    except OSError as e:
        console.print(
            Panel(
                f"Error: Unable to create output directory '{output_dir}'.\n{e}",
                title="Error",
                style="red"
            )
        )
        sys.exit(1)


def init_config():
    """
    Load or create a default vrip.ini config in the OS-specific location.
      - Windows: C:\\vrip_tools\\vrip.ini
      - Linux:   ~/programs/vrip-ini/vrip.ini
    """
    config_path = get_config_path()
    config_dir = os.path.dirname(config_path)

    if not os.path.exists(config_dir):
        os.makedirs(config_dir, exist_ok=True)

    config = configparser.ConfigParser()

    if os.path.exists(config_path):
        # Load existing config
        config.read(config_path)
        console.print(
            Panel(
                f"Loading existing config from:\n{config_path}",
                title="Config",
                style="blue"
            )
        )
    else:
        # Create a brand-new config with default values
        console.print(
            Panel(
                f"Config not found. Creating default config at:\n{config_path}",
                title="Config",
                style="yellow"
            )
        )
        config["user"] = {
            "name": "",
            "password": "",
        }
        config["system"] = {
            "os": platform.system().lower(),
            # Let’s store a default output directory, can be changed via config
            "default_output_dir": r"C:\vrip_tools\downloads" if "windows" in platform.system().lower()
            else os.path.join(os.path.expanduser("~"), "podcasts")
        }
        config["logging"] = {
            # Where logs will be stored, can change in config
            "log_dir": r"C:\vrip_tools\logs" if "windows" in platform.system().lower()
            else os.path.join(os.path.expanduser("~"), "pylogs", "vrip"),
            # Default logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL
            "log_level": "INFO"
        }
        with open(config_path, "w") as configfile:
            config.write(configfile)
        console.print(
            Panel("Default vrip.ini created.", title="Config", style="green")
        )

    return config, config_path


def setup_logging():
    """Enable session logging based on the config file."""
    config, _ = init_config()
    log_dir = config["logging"].get("log_dir", "")
    log_level_str = config["logging"].get("log_level", "INFO")

    # Convert string to actual logging level
    numeric_level = getattr(logging, log_level_str.upper(), None)
    if not isinstance(numeric_level, int):
        numeric_level = logging.INFO  # fallback

    try:
        os.makedirs(log_dir, exist_ok=True)
    except OSError as e:
        console.print(
            Panel(
                f"Error: Unable to create log directory '{log_dir}'.\n{e}",
                title="Error",
                style="red"
            )
        )
        # We can continue but logs won't be written properly
        log_dir = ""

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = os.path.join(log_dir, f"session_{timestamp}.log") if log_dir else None

    logging.basicConfig(
        filename=log_file if log_file else None,
        filemode="w",
        format="%(asctime)s - %(levelname)s - %(message)s",
        level=numeric_level
    )

    if log_file:
        console.print(
            Panel(
                f"Session logs will be saved to:\n{log_file}",
                title="Logging",
                style="green"
            )
        )
    else:
        console.print(
            Panel(
                "Logging to console only (no log file directory).",
                title="Logging",
                style="yellow"
            )
        )

    # Optional: Log a start-of-session message
    logging.info("Logging initialized.")


def validate_config():
    """
    Interactive check to ensure user name, password, system OS, etc. are set in vrip.ini.
    """
    config, config_path = init_config()
    changed = False

    if "user" not in config:
        config["user"] = {}
    if "system" not in config:
        config["system"] = {}

    # Prompt for user name
    if not config["user"].get("name"):
        console.print(
            Panel(
                "No user name found. Let's fix that.",
                title="Config Update",
                style="yellow"
            )
        )
        config["user"]["name"] = console.input("[blue]Enter your name: [/blue]")
        changed = True

    # Prompt for password
    if not config["user"].get("password"):
        console.print(
            Panel(
                "No password found. Let's fix that.",
                title="Config Update",
                style="yellow"
            )
        )
        config["user"]["password"] = console.input("[blue]Enter your password: [/blue]")
        changed = True

    # Ensure 'system' section has OS
    if not config["system"].get("os"):
        console.print(
            Panel(
                "No OS info found. Let's fix that.",
                title="Config Update",
                style="yellow"
            )
        )
        config["system"]["os"] = platform.system().lower()
        changed = True

    if changed:
        with open(config_path, "w") as f:
            config.write(f)
        console.print(
            Panel(
                "Configuration updated successfully!",
                title="Config",
                style="green"
            )
        )
    else:
        console.print(
            Panel(
                "Configuration is already good to go.",
                title="Config",
                style="green"
            )
        )


def install_dependencies_windows(verbose=False):
    """
    Install required dependencies for Windows using Chocolatey (if relevant).
    Possibly just logging that we 'would' install, or no-ops if none needed.
    """
    console.print(Panel("Checking/Installing dependencies (Windows)...", style="blue"))
    # Example logic: If you need `ffmpeg`, `python-requests`, etc. installed system-wide
    # This is just a placeholder—real usage might vary.
    # You can also disable or remove if not needed for your environment.
    if verbose:
        console.print(Panel("Would run: choco install <deps>", style="cyan"))

    console.print(Panel("Dependencies checked (Windows).", style="green"))


def install_dependencies_linux(verbose=False):
    """
    Install required dependencies for Linux using apt-get (if relevant).
    Possibly just logging that we 'would' install, or no-ops if none needed.
    """
    console.print(Panel("Checking/Installing dependencies (Linux)...", style="blue"))
    if verbose:
        console.print(Panel("Would run: sudo apt-get install <deps>", style="cyan"))

    console.print(Panel("Dependencies checked (Linux).", style="green"))


def download_with_progress(url, output_path, description="Downloading"):
    """Download a file with a progress bar showing MB and percentage."""
    response = requests.get(url, stream=True)
    total_size = int(response.headers.get('content-length', 0))

    with open(output_path, 'wb') as file, Progress(
            TextColumn("[bold blue]{task.description}[/bold blue]"),
            BarColumn(),
            MBPercentColumn(),
            TimeElapsedColumn(),
            console=console
    ) as progress:
        task = progress.add_task(description, total=total_size)
        for chunk in response.iter_content(chunk_size=8192):
            file.write(chunk)
            progress.update(task, advance=len(chunk))

    console.print(
        Panel(
            f"Download complete! Saved at:\n{output_path}",
            title="Download",
            style="green"
        )
    )
    logging.info(f"Downloaded: {url} -> {output_path}")


def download_podcast_rss(rss_url, output_dir, count=None, searchby=None, verbose=False):
    """Download episodes from a podcast RSS feed."""
    logging.info(f"Starting RSS download from: {rss_url}, output_dir={output_dir}, count={count}, searchby={searchby}")

    if verbose:
        console.print(
            Panel(
                f"Fetching RSS feed from:\n{rss_url}\nOutput directory:\n{output_dir}",
                title="Podcast RSS",
                style="blue"
            )
        )
    ensure_output_dir(output_dir)
    feed = feedparser.parse(rss_url)

    if not feed.entries:
        console.print(
            Panel(
                f"No episodes found in RSS feed:\n{rss_url}",
                title="Podcast RSS",
                style="yellow"
            )
        )
        logging.warning("No entries found in RSS feed.")
        return

    # Filter by search term if provided
    filtered_entries = (
        [entry for entry in feed.entries if searchby.lower() in entry.title.lower()]
        if searchby else feed.entries
    )
    entries_to_download = filtered_entries[:count] if count else filtered_entries

    if not entries_to_download:
        console.print(
            Panel(
                f"No episodes found matching the search term:\n'{searchby}'",
                title="Podcast RSS",
                style="yellow"
            )
        )
        logging.warning(f"No entries match search term '{searchby}'.")
        return

    # Download each
    for index, entry in enumerate(entries_to_download, start=1):
        title = entry.title
        link = entry.enclosures[0].href if entry.enclosures else None

        if not link:
            console.print(
                Panel(
                    f"Skipping episode '{title}' (no downloadable link found).",
                    title="Podcast RSS",
                    style="yellow"
                )
            )
            logging.warning(f"No enclosure found for episode: {title}")
            continue

        # Sanitize the title for a filename
        sanitized_title = "".join(c for c in title if c.isalnum() or c in " _-").rstrip()
        file_path = os.path.join(output_dir, f"{sanitized_title}.mp3")

        if verbose:
            console.print(
                Panel(
                    f"Downloading podcast episode:\n{title}\nEpisode link:\n{link}\nSaving to:\n{file_path}",
                    title="Podcast RSS",
                    style="blue"
                )
            )

        try:
            download_with_progress(link, file_path, description=f"Podcast {index}/{len(entries_to_download)}")
        except requests.RequestException as e:
            console.print(
                Panel(
                    f"Error downloading episode '{title}': {e}",
                    title="Error",
                    style="red"
                )
            )
            logging.exception(f"Error downloading episode '{title}'")
            continue

        clear_screen()


def manage_settings_config():
    """Create, edit, or view vrip.ini from the known OS-specific path."""
    config, config_path = init_config()
    console.print(Panel("Settings management selected.", title="Settings", style="blue"))

    action = console.input("[yellow]Choose an action (view/edit): [/yellow]").strip().lower()

    if action == "view":
        if os.path.exists(config_path):
            with open(config_path, "r") as configfile:
                content = configfile.read()
            console.print(Panel(content, title="vrip.ini contents", style="blue"))
        else:
            console.print(Panel("No config file found!", title="Error", style="red"))

    elif action == "edit":
        validate_config()
        # Optionally allow editing other fields like default_output_dir, etc.
        edit_more = console.input(
            "[yellow]Do you want to edit advanced settings (output dir, logging)? (y/n): [/yellow]").strip().lower()
        if edit_more == 'y':
            changed = False
            # Reload config in case validate_config changed it
            config, config_path = init_config()

            # 1) Default output directory
            current_output_dir = config["system"].get("default_output_dir", "")
            new_output_dir = console.input(
                f"[blue]Current default output dir:[/blue] {current_output_dir}\nEnter new dir (blank=keep current): ").strip()
            if new_output_dir:
                config["system"]["default_output_dir"] = new_output_dir
                changed = True

            # 2) Log directory
            current_log_dir = config["logging"].get("log_dir", "")
            new_log_dir = console.input(
                f"[blue]Current log directory:[/blue] {current_log_dir}\nEnter new dir (blank=keep current): ").strip()
            if new_log_dir:
                config["logging"]["log_dir"] = new_log_dir
                changed = True

            # 3) Log level
            current_log_level = config["logging"].get("log_level", "INFO")
            new_log_level = console.input(
                f"[blue]Current log level:[/blue] {current_log_level}\nEnter new level (DEBUG/INFO/WARNING/ERROR/CRITICAL) or blank to keep current: ").strip().upper()
            valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
            if new_log_level and new_log_level in valid_levels:
                config["logging"]["log_level"] = new_log_level
                changed = True

            # Save changes
            if changed:
                with open(config_path, "w") as cf:
                    config.write(cf)
                console.print(Panel("Configuration updated!", style="green"))
            else:
                console.print(Panel("No advanced settings changed.", style="green"))
    else:
        console.print(Panel("Invalid action. Please choose 'view' or 'edit'.", title="Error", style="red"))


def handle_setup_command():
    """Display the setup menu for managing configuration or installing dependencies."""
    menu_text = (
        "[bold]Setup Menu[/bold]\n"
        "1) Manage config (view/edit vrip.ini)\n"
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
        console.print(
            Panel(
                f"Auto-detected OS: {current_os}",
                title="Auto-detect",
                style="yellow"
            )
        )
        if "linux" in current_os:
            install_dependencies_linux(verbose=True)
        elif "windows" in current_os:
            install_dependencies_windows(verbose=True)
        else:
            console.print(
                Panel(
                    "Unsupported OS or detection failed.",
                    title="Error",
                    style="red"
                )
            )
    elif choice == "5":
        return
    else:
        console.print(Panel("Invalid choice.", title="Error", style="red"))


def handle_init_command():
    """
    Auto-detect OS, 'install dependencies', create or load vrip.ini,
    and prompt for any missing details.
    """
    current_os = platform.system().lower()
    console.print(Panel(f"Running 'init' command for OS = {current_os}",
                        title="Init", style="blue"))

    if "windows" in current_os:
        install_dependencies_windows(verbose=True)
    elif "linux" in current_os:
        install_dependencies_linux(verbose=True)
    else:
        console.print(
            Panel(
                "Unsupported OS detected. Abort.",
                title="Error",
                style="red"
            )
        )
        return

    init_config()
    validate_config()
    console.print(
        Panel(
            "Initialization complete!",
            title="Init",
            style="green"
        )
    )


def handle_man_command():
    """Display a thorough manual explaining how to use the vrip script (RSS-only)."""
    manual_text = f"""
[bold cyan]NAME[/bold cyan]
    vrip (RSS-Only Edition) - A command-line tool for downloading audio from podcast RSS feeds.

[bold cyan]DESCRIPTION[/bold cyan]
    A menu-driven version of vrip that:
      - Manages config via vrip.ini (stored on Windows in C:\\vrip_tools\\, or on Linux in ~/programs/vrip-ini/).
      - Installs dependencies if needed.
      - Downloads podcast episodes from an RSS feed, optionally filtering by title.

[bold cyan]MENU OPTIONS[/bold cyan]
    1) init - Auto-detect OS, install dependencies, and configure vrip.ini.
    2) setup - Manually install dependencies or manage vrip.ini (view/edit).
    3) download - Download audio from a podcast RSS feed (with optional search term).
    4) man - Display this manual.
    5) exit - Quit the tool.

[bold cyan]CONFIGURATION[/bold cyan]
    [system]
    os = windows or linux
    default_output_dir = (Where your downloads go by default)

    [logging]
    log_dir = (Where your logs are stored)
    log_level = INFO (Default logging level)

[bold cyan]VERSION[/bold cyan]
    {VERSION}

[bold cyan]AUTHOR[/bold cyan]
    Maintained by [Your Project/Name].

[bold cyan]COPYRIGHT[/bold cyan]
    Distributed under the MIT License.
"""
    console.print(Panel(manual_text, title="Manual", style="white"))


def handle_download_command():
    """Present a menu to download from a podcast RSS."""
    console.print(
        Panel(
            "[bold]Download Menu[/bold]\n"
            "1) Download from podcast RSS\n"
            "2) Return to main menu",
            title="Download",
            style="cyan"
        )
    )
    choice = console.input("\nEnter choice: ").strip()

    # Load default output dir from config
    config, _ = init_config()
    default_download_dir = config["system"].get("default_output_dir", "")

    if choice == "1":
        rss_url = console.input("Enter RSS URL (e.g. https://site/feed.xml): ").strip()
        if not rss_url:
            console.print(Panel("Invalid RSS URL. Returning to menu.", title="Error", style="red"))
            return

        count_str = console.input("How many recent episodes to download? (Leave blank for all): ").strip()
        try:
            count = int(count_str) if count_str else None
        except ValueError:
            console.print(Panel("Invalid number, ignoring.", title="Warning", style="red"))
            count = None

        search_by = console.input("Enter search term for titles (leave blank for no filter): ").strip()
        directory = console.input(
            f"Enter output directory [default: {default_download_dir}]: ").strip() or default_download_dir
        ensure_output_dir(directory)

        enable_logging = console.input("Enable session logging? (y/n): ").strip().lower() == 'y'
        verbose = console.input("Enable verbose output? (y/n): ").strip().lower() == 'y'
        if enable_logging:
            setup_logging()

        download_podcast_rss(rss_url, directory, count=count, searchby=search_by, verbose=verbose)

    elif choice == "2":
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
            "3) download (RSS)\n"
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
            console.print(Panel("Invalid choice, please try again.", title="Error", style="red"))


if __name__ == "__main__":
    main()
