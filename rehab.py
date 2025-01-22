#!/home/sohfix/PycharmProjects/rehab/renv/bin/python3

import os
import subprocess
import argparse
import sys
import requests
import feedparser
from rich.console import Console
from rich.progress import Progress, BarColumn, TextColumn

console = Console()


def ensure_output_dir(output_dir):
    """
    Ensure the output directory exists, creating it if necessary.
    """
    try:
        os.makedirs(output_dir, exist_ok=True)
    except OSError as e:
        console.print(f"[red]Error:[/red] Unable to create output directory '{output_dir}'. {e}", style="bold red")
        sys.exit(1)


def install_dependencies(verbose=False):
    """
    Install dependencies from requirements.txt using pip.
    """
    requirements_file = os.path.join(os.path.dirname(__file__), "requirements.txt")

    if not os.path.isfile(requirements_file):
        console.print(f"[red]Error:[/red] requirements.txt not found at {requirements_file}", style="bold red")
        sys.exit(1)

    command = [sys.executable, "-m", "pip", "install", "-r", requirements_file]

    if not verbose:
        command.append("--quiet")

    console.print(f"[blue]Installing dependencies from {requirements_file}...[/blue]")
    try:
        with Progress(
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                console=console
        ) as progress:
            task = progress.add_task("Installing dependencies...", total=None)
            subprocess.run(command, check=True)
            progress.update(task, completed=100)

        console.print("[green]Dependencies installed successfully![/green]")
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Error:[/red] Failed to install dependencies. {e}", style="bold red")
        sys.exit(1)


def download_audio(url, output_file, cookies_file=None, debug=False, verbose=False):
    """
    Download audio from a URL using yt-dlp and save it as an MP3 file.
    """
    command = [
        "yt-dlp",
        "-x", "--audio-format", "mp3",
        "-o", output_file,
        url
    ]

    if cookies_file:
        command.extend(["--cookies", cookies_file])

    if debug:
        console.print(f"[yellow][DEBUG][/yellow] Running command: {' '.join(command)}")

    console.print(f"[blue]Downloading audio from:[/blue] {url}")
    try:
        with Progress(
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                console=console
        ) as progress:
            task = progress.add_task("Downloading...", total=None)
            subprocess.run(command, check=True)
            progress.update(task, completed=100)

        console.print(f"[green]Download complete! Saved to:[/green] {output_file}")
    except FileNotFoundError:
        console.print("[red]Error:[/red] yt-dlp is not installed. Install it with 'pip install yt-dlp'.",
                      style="bold red")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Error:[/red] Failed to download audio. {e}", style="bold red")
        sys.exit(1)


def get_title_from_url(url, debug=False, verbose=False):
    """
    Fetch the title of a YouTube video (or other supported site) using yt-dlp.
    """
    if verbose:
        console.print(f"[blue]Retrieving title for URL:[/blue] {url}")

    command = ["yt-dlp", "--get-title", url]

    if debug:
        console.print(f"[yellow][DEBUG][/yellow] Running command: {' '.join(command)}")

    try:
        result = subprocess.run(command, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        title = result.stdout.strip()
        return "".join(c for c in title if c.isalnum() or c in " _-").rstrip()
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to retrieve title from URL. {e}")


def download_from_file(file_path, base_output_dir, use_title=False, cookies_file=None, debug=False, verbose=False):
    """
    Download multiple audio files from a text file containing section headers and URLs.
    Organizes downloads into subdirectories based on sections.
    """
    if not os.path.isfile(file_path):
        console.print(f"[red]Error:[/red] File '{file_path}' does not exist.", style="bold red")
        sys.exit(1)

    if verbose:
        console.print(f"[blue]Starting bulk download from file:[/blue] {file_path}")
        console.print(f"[blue]Base output directory:[/blue] {base_output_dir}")

    try:
        current_section = None

        with open(file_path, 'r') as file:
            for line in file:
                line = line.strip()
                if not line:
                    continue

                if line.startswith("[") and line.endswith("]"):
                    current_section = line[1:-1]
                    if verbose:
                        console.print(f"[yellow]Detected new section:[/yellow] {current_section}")
                    continue

                if not current_section:
                    console.print(f"[red]Error:[/red] Found URL without a section: {line}", style="bold red")
                    continue

                section_dir = os.path.join(base_output_dir, current_section)
                ensure_output_dir(section_dir)

                if not use_title:
                    try:
                        file_name, url = line.split('" "')
                        file_name = file_name.strip('"')
                        url = url.strip('"')
                    except ValueError:
                        console.print(
                            f"[red]Error:[/red] Invalid format in line: {line}. Expected format: \"filename.mp3\" \"url\"",
                            style="bold red")
                        continue
                else:
                    url = line.strip('"')
                    try:
                        file_name = get_title_from_url(url, debug=debug, verbose=verbose) + ".mp3"
                    except Exception as e:
                        console.print(f"[red]Error:[/red] Unable to retrieve title from URL '{url}': {e}",
                                      style="bold red")
                        continue

                output_file = os.path.join(section_dir, file_name)

                if verbose:
                    console.print(f"[blue]Downloading file:[/blue] {file_name}")
                    console.print(f"[blue]  from URL:[/blue] {url}")
                    console.print(f"[blue]  into directory:[/blue] {section_dir}")

                download_audio(url, output_file, cookies_file=cookies_file, debug=debug, verbose=verbose)

    except Exception as e:
        console.print(f"[red]Error:[/red] Unable to process file '{file_path}'. {e}", style="bold red")
        sys.exit(1)


def download_podcast_rss(rss_url, output_dir, debug=False, verbose=False):
    """
    Download all episodes from a podcast RSS feed.
    """
    if verbose:
        console.print(f"[blue]Fetching RSS feed from:[/blue] {rss_url}")
        console.print(f"[blue]Output directory:[/blue] {output_dir}")

    ensure_output_dir(output_dir)
    feed = feedparser.parse(rss_url)

    if not feed.entries:
        console.print(f"[yellow]No episodes found in RSS feed:[/yellow] {rss_url}")
        return

    for entry in feed.entries:
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
            with Progress(
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                    console=console
            ) as progress:
                task = progress.add_task("Downloading...", total=None)
                response = requests.get(link, stream=True)
                response.raise_for_status()
                with open(file_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                    progress.update(task, completed=100)
            console.print(f"[green]Saved:[/green] {file_path}")
        except requests.RequestException as e:
            console.print(f"[red]Error downloading episode '{title}':[/red] {e}", style="bold red")


def record_audio(output_file, device="default", debug=False, verbose=False, duration=None, bitrate="128k",
                 sample_rate="44100"):
    """
    Record audio from the specified system input device using FFmpeg.
    Press Ctrl+C or terminate the process to stop recording.
    """
    ffmpeg_input = ["-f", "alsa", "-i", device]

    if verbose:
        console.print("[blue]Starting audio recording with the following parameters:[/blue]")
        console.print(f"  [blue]Output file:[/blue] {output_file}")
        console.print(f"  [blue]Device:[/blue] {device}")
        console.print(f"  [blue]Duration:[/blue] {duration if duration else 'unlimited (until stopped)'}")
        console.print(f"  [blue]Bitrate:[/blue] {bitrate}")
        console.print(f"  [blue]Sample rate:[/blue] {sample_rate}")
        console.print("[blue]Press Ctrl+C to stop the recording whenever you're done.[/blue]")

    command = [
                  "ffmpeg",
                  "-y",
              ] + ffmpeg_input + [
                  "-vn",
                  "-acodec", "libmp3lame",
                  "-ab", bitrate,
                  "-ar", sample_rate,
              ]

    if duration is not None:
        command.extend(["-t", str(duration)])

    command.append(output_file)

    if debug:
        console.print(f"[yellow][DEBUG][/yellow] FFmpeg command: {' '.join(command)}")

    try:
        subprocess.run(command, check=True)
    except FileNotFoundError:
        console.print("[red]Error:[/red] ffmpeg not found. Please install ffmpeg and try again.", style="bold red")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Error:[/red] ffmpeg failed to record audio. {e}", style="bold red")
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[blue]Recording stopped by user.[/blue]")
        sys.exit(0)


def show_manual():
    """
    Print a detailed, mini-manual of all commands and arguments for the user.
    """
    manual_text = r"""
===========================
 REHAB: MINI-MANUAL
===========================
This script can INSTALL dependencies, DOWNLOAD audio, RECORD from a system input,
and also display this MANUAL. Below is a summary of each command and its arguments.
...
"""
    console.print(manual_text)


def main():
    parser = argparse.ArgumentParser(description="Rehab: Audio Recorder, Splitter, and Downloader", add_help=True)
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Install Command
    install_parser = subparsers.add_parser("install", help="Install dependencies from requirements.txt")
    install_parser.add_argument("--verbose", action="store_true", help="Show detailed installation logs.")

    # Download Command
    download_parser = subparsers.add_parser("download",
                                            help="Download audio as MP3 from a URL, text file, or RSS feed.")
    download_parser.add_argument("url", nargs="?", help="URL of the audio/video to download (e.g. YouTube link).")
    download_parser.add_argument("-o", "--output", default="./downloads/audio.mp3",
                                 help="Output file path for a single download.")
    download_parser.add_argument("-f", "--file",
                                 help="Text file with filename and URL pairs, possibly in section headers.")
    download_parser.add_argument("-d", "--dir", default="./downloads",
                                 help="Base output directory for multiple downloads.")
    download_parser.add_argument("--rss",
                                 help="Download audio files from a podcast RSS feed (e.g., https://site/feed.xml).")
    download_parser.add_argument("--use-title", action="store_true",
                                 help="Use the content's title (via yt-dlp) as the filename.")
    download_parser.add_argument("--cookies", help="Path to cookies file for authenticated downloads.")
    download_parser.add_argument("--debug", action="store_true", help="Show the yt-dlp command used for debugging.")
    download_parser.add_argument("--verbose", action="store_true",
                                 help="Show additional messages explaining each step.")

    # Record Command
    rec_parser = subparsers.add_parser("rec", help="Record audio from a system input device and save as MP3.")
    rec_parser.add_argument("--name", required=True, help="Base filename (without the .mp3 extension).")
    rec_parser.add_argument("-o", "--output-dir", default="./recordings", help="Directory to save the MP3 file.")
    rec_parser.add_argument("--device", default="default", help="Audio input device name.")
    rec_parser.add_argument("--duration", type=int, help="Maximum number of seconds to record (omit for unlimited).")
    rec_parser.add_argument("--bitrate", default="128k", help="MP3 encoding bitrate.")
    rec_parser.add_argument("--sample-rate", default="44100", help="MP3 sample rate in Hz.")
    rec_parser.add_argument("--debug", action="store_true", help="Display the ffmpeg command for debugging.")
    rec_parser.add_argument("--verbose", action="store_true", help="Print detailed messages during recording.")

    # Manual Command
    manual_parser = subparsers.add_parser("manual", help="Display a mini-manual with extended usage instructions.")

    args = parser.parse_args()

    if args.command == "install":
        install_dependencies(verbose=args.verbose)
    elif args.command == "download":
        if args.rss:
            download_podcast_rss(args.rss, args.dir, debug=args.debug, verbose=args.verbose)
        elif args.file:
            download_from_file(args.file, args.dir, use_title=args.use_title, cookies_file=args.cookies,
                               debug=args.debug, verbose=args.verbose)
        elif args.url:
            ensure_output_dir(os.path.dirname(args.output))
            download_audio(args.url, args.output, cookies_file=args.cookies, debug=args.debug, verbose=args.verbose)
        else:
            console.print("[red]Error:[/red] You must specify a URL, file, or RSS feed for the download.",
                          style="bold red")
            sys.exit(1)
    elif args.command == "rec":
        ensure_output_dir(args.output_dir)
        output_file = os.path.join(args.output_dir, f"{args.name}.mp3")
        record_audio(output_file, device=args.device, debug=args.debug, verbose=args.verbose, duration=args.duration,
                     bitrate=args.bitrate, sample_rate=args.sample_rate)
    elif args.command == "manual":
        show_manual()


if __name__ == "__main__":
    main()
