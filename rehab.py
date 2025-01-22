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

console = Console()

def ensure_output_dir(output_dir):
    """Ensure the output directory exists, creating it if necessary."""
    try:
        os.makedirs(output_dir, exist_ok=True)
    except OSError as e:
        console.print(f"[red]Error:[/red] Unable to create output directory '{output_dir}'. {e}", style="bold red")
        sys.exit(1)

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
            with requests.get(link, stream=True) as response:
                response.raise_for_status()
                total_size = int(response.headers.get("content-length", 0))

                with Progress(
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                    console=console
                ) as progress:
                    task = progress.add_task("Downloading...", total=total_size)
                    with open(file_path, "wb") as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                            progress.update(task, advance=len(chunk))

            console.print(f"[green]Saved:[/green] {file_path}")
        except requests.RequestException as e:
            console.print(f"[red]Error downloading episode '{title}':[/red] {e}", style="bold red")

def download_youtube_with_pytube(url, output_dir, audio_only=False, use_title=False, set_title=None, verbose=False):
    """Download a YouTube video or its audio content using pytube."""
    ensure_output_dir(output_dir)

    if verbose:
        console.print(f"[blue]Downloading from YouTube URL:[/blue] {url}")
        console.print(f"[blue]Output directory:[/blue] {output_dir}")

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

def download_youtube_with_ytdlp(url, output_dir, audio_only=False, use_title=False, set_title=None, verbose=False):
    """Download a YouTube video or its audio content using yt-dlp."""
    ensure_output_dir(output_dir)

    if verbose:
        console.print(f"[blue]Downloading from YouTube URL using yt-dlp:[/blue] {url}")
        console.print(f"[blue]Output directory:[/blue] {output_dir}")

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

def main():
    parser = argparse.ArgumentParser(description="Rehab: Audio Recorder, Splitter, and Downloader", add_help=True)
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Download Command
    download_parser = subparsers.add_parser("download", help="Download audio as MP3 from a URL, text file, or RSS feed.")
    download_parser.add_argument("-d", "--dir", default="$HOME/Desktop/Audio", help="Base output directory for downloads.")
    download_parser.add_argument("--rss", help="Download audio files from a podcast RSS feed (e.g., https://site/feed.xml).")
    download_parser.add_argument("-c", "--count", type=int, help="Number of most recent episodes to download.")
    download_parser.add_argument("--searchby", help="String to search for in podcast titles.")
    download_parser.add_argument("--youtube", help="Download content from a YouTube URL.")
    download_parser.add_argument("--audio-only", action="store_true", help="Download only audio as MP3.")
    download_parser.add_argument("--use-title", action="store_true", help="Use the YouTube video's title.")
    download_parser.add_argument("--set-title", help="Set a custom title for the downloaded YouTube content.")
    download_parser.add_argument("--yt-dlp", action="store_true", help="Use yt-dlp instead of pytube for downloading YouTube content.")
    download_parser.add_argument("--debug", action="store_true", help="Show debugging information.")
    download_parser.add_argument("--verbose", action="store_true", help="Show additional messages explaining each step.")

    args = parser.parse_args()

    if args.command == "download":
        if args.rss:
            download_podcast_rss(
                rss_url=args.rss,
                output_dir=args.dir,
                count=args.count,
                searchby=args.searchby,
                debug=args.debug,
                verbose=args.verbose
            )
        if args.youtube:
            if args.yt_dlp:
                download_youtube_with_ytdlp(
                    url=args.youtube,
                    output_dir=args.dir,
                    audio_only=args.audio_only,
                    use_title=args.use_title,
                    set_title=args.set_title,
                    verbose=args.verbose
                )
            else:
                download_youtube_with_pytube(
                    url=args.youtube,
                    output_dir=args.dir,
                    audio_only=args.audio_only,
                    use_title=args.use_title,
                    set_title=args.set_title,
                    verbose=args.verbose
                )

if __name__ == "__main__":
    main()
