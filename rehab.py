#!/home/sohfix/PycharmProjects/rehab/renv/bin/python3
import os
import subprocess
import argparse
import sys
import requests
import feedparser


def ensure_output_dir(output_dir):
    """
    Ensure the output directory exists, creating it if necessary.
    """
    try:
        os.makedirs(output_dir, exist_ok=True)
    except OSError as e:
        print(f"Error: Unable to create output directory '{output_dir}'. {e}")
        sys.exit(1)


def install_dependencies(verbose=False):
    """
    Install dependencies from requirements.txt using pip.
    """
    requirements_file = os.path.join(os.path.dirname(__file__), "requirements.txt")

    # Check if requirements.txt exists
    if not os.path.isfile(requirements_file):
        print(f"Error: requirements.txt not found at {requirements_file}")
        sys.exit(1)

    # Construct the pip command
    command = [sys.executable, "-m", "pip", "install", "-r", requirements_file]
    if verbose:
        print("Running in verbose mode...")
    else:
        command.append("--quiet")

    # Run the pip command
    try:
        print(f"Installing dependencies from {requirements_file}...")
        subprocess.run(command, check=True)
        print("Dependencies installed successfully!")
    except subprocess.CalledProcessError as e:
        print(f"Error: Failed to install dependencies. {e}")
        sys.exit(1)


def download_audio(url, output_file, debug=False):
    """
    Download audio from a URL using yt-dlp and save it as an MP3 file.
    Includes a --force flag to bypass restrictions.
    """
    command = [
        "yt-dlp",
        "--force-generic-extractor",  # Use this to force the extractor
        "-x", "--audio-format", "mp3",
        "-o", output_file,
        url
    ]
    if debug:
        print("Running command:", " ".join(command))
    print(f"Downloading audio from: {url}")
    try:
        subprocess.run(command, check=True)
        print(f"Download complete. Saved to: {output_file}")
    except FileNotFoundError:
        print("Error: yt-dlp is not installed. Install it with 'pip install yt-dlp'.")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"Error: Failed to download audio. {e}")
        sys.exit(1)


def get_title_from_url(url):
    """
    Fetch the title of a YouTube video using yt-dlp.
    """
    command = [
        "yt-dlp",
        "--get-title",
        url
    ]
    try:
        result = subprocess.run(command, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        title = result.stdout.strip()
        return "".join(c for c in title if c.isalnum() or c in " _-").rstrip()  # Sanitize the title
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to retrieve title from URL. {e}")


def download_from_file(file_path, base_output_dir, use_title=False, debug=False):
    """
    Download multiple audio files from a text file containing section headers and URLs.
    Organizes downloads into subdirectories based on sections.
    """
    if not os.path.isfile(file_path):
        print(f"Error: File '{file_path}' does not exist.")
        sys.exit(1)

    try:
        current_section = None

        with open(file_path, 'r') as file:
            for line in file:
                line = line.strip()

                # Skip empty lines
                if not line:
                    continue

                # Detect section headers (e.g., [songs], [mixes])
                if line.startswith("[") and line.endswith("]"):
                    current_section = line[1:-1]  # Extract section name
                    continue

                # Ensure we are inside a valid section
                if not current_section:
                    print(f"Error: Found URL without a section: {line}")
                    continue

                # Determine subdirectory for the current section
                section_dir = os.path.join(base_output_dir, current_section)
                ensure_output_dir(section_dir)

                if not use_title:
                    # Parse filename and URL
                    try:
                        file_name, url = line.split('" "')
                        file_name = file_name.strip('"')
                        url = url.strip('"')
                    except ValueError:
                        print(f"Error: Invalid format in line: {line}. Expected format: \"filename.mp3\" \"url\"")
                        continue
                else:
                    # Use the title from the URL
                    url = line.strip('"')
                    try:
                        file_name = get_title_from_url(url) + ".mp3"
                    except Exception as e:
                        print(f"Error: Unable to retrieve title from URL '{url}': {e}")
                        continue

                # Full output file path
                output_file = os.path.join(section_dir, file_name)

                # Download the audio
                print(f"Downloading: {file_name} from {url} into {section_dir}")
                download_audio(url, output_file, debug=debug)

    except Exception as e:
        print(f"Error: Unable to process file '{file_path}'. {e}")
        sys.exit(1)


def download_podcast_rss(rss_url, output_dir):
    """
    Download all episodes from a podcast RSS feed.
    """
    ensure_output_dir(output_dir)

    print(f"Fetching RSS feed from: {rss_url}")
    feed = feedparser.parse(rss_url)

    if not feed.entries:
        print(f"No episodes found in RSS feed: {rss_url}")
        return

    # Loop through episodes
    for entry in feed.entries:
        title = entry.title
        link = entry.enclosures[0].href if entry.enclosures else None

        if not link:
            print(f"Skipping episode '{title}' (no downloadable link found).")
            continue

        # Sanitize title for filename
        sanitized_title = "".join(c for c in title if c.isalnum() or c in " _-").rstrip()
        file_path = os.path.join(output_dir, f"{sanitized_title}.mp3")

        # Download the episode
        print(f"Downloading: {title}")
        try:
            response = requests.get(link, stream=True)
            response.raise_for_status()
            with open(file_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            print(f"Saved: {file_path}")
        except requests.RequestException as e:
            print(f"Error downloading episode '{title}': {e}")


def main():
    """
    Main function to parse arguments and execute commands.
    """
    parser = argparse.ArgumentParser(description="Rehab: Audio Recorder, Splitter, and Downloader")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Install command
    install_parser = subparsers.add_parser("install", help="Install dependencies from requirements.txt")
    install_parser.add_argument("--verbose", action="store_true", help="Show detailed installation logs")

    # Download command
    download_parser = subparsers.add_parser("download", help="Download audio as MP3 from a URL, text file, or RSS feed")
    download_parser.add_argument("url", nargs="?", help="URL of the audio to download")
    download_parser.add_argument("-o", "--output", default="./downloads/audio.mp3",
                                 help="Output file path for single download (default: ./downloads/audio.mp3)")
    download_parser.add_argument("-f", "--file", help="Text file with filename and URL pairs for bulk download")
    download_parser.add_argument("-d", "--dir", default="./downloads",
                                 help="Base output directory for bulk downloads (default: ./downloads)")
    download_parser.add_argument("--rss", help="RSS feed URL for downloading podcast episodes")
    download_parser.add_argument("--use-title", action="store_true",
                                 help="Use video titles for filenames when downloading from file")
    download_parser.add_argument("--debug", action="store_true", help="Show detailed download commands for debugging")

    args = parser.parse_args()

    # Execute the selected command
    if args.command == "install":
        install_dependencies(verbose=args.verbose)
    elif args.command == "download":
        if args.rss:
            download_podcast_rss(args.rss, args.dir)
        elif args.file:
            download_from_file(args.file, args.dir, args.use_title, debug=args.debug)
        elif args.url:
            ensure_output_dir(os.path.dirname(args.output))
            download_audio(args.url, args.output, debug=args.debug)
        else:
            print("Error: You must specify a URL, file, or RSS feed for the download.")
            sys.exit(1)


if __name__ == "__main__":
    main()