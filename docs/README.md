# Rehab: Audio Recorder, Splitter, and Downloader

![Version](https://img.shields.io/badge/version-1.0.3-green)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

A powerful command-line tool to download and manage audio files. **Rehab** supports YouTube videos, podcast RSS feeds. Backed by Python, `ffmpeg`, and `yt-dlp`, Rehab streamlines your audio workflow with an intuitive interface.

---

## Table of Contents
- [Features](#features)
- [Installation](#installation)
  - [Prerequisites](#prerequisites)
  - [Steps](#steps)
- [Usage](#usage)
  - [General Structure](#general-structure)
  - [Commands](#commands)
    - [setup](#setup)
    - [download](#download)
- [Directory Structure](#directory-structure)
- [Contributing](#contributing)
- [License](#license)
- [Contact](#contact)

---

## Features

- **Audio Downloading**  
  Download audio files from YouTube, RSS feeds, or direct URLs. Convert videos into MP3 or MP4 with audio-only mode.

- **System Audio Recording**  
  Record system audio input using `ffmpeg` with customizable duration and output.

- **Enhanced User Experience**  
  - Progress bars and color-rich output using the `rich` library  
  - Comprehensive error handling and logging

- **Setup Automation**  
  - `setup` command to auto-configure dependencies  
  - Interactive INI file configuration

- **Cross-Platform Compatibility**  
  Works on Linux, macOS, and Windows.

---

## Installation

### Prerequisites

Ensure the following are installed:
- **Python**: Version 3.8 or higher.
- **ffmpeg**: Required for audio recording.
- **yt-dlp**: For downloading YouTube videos and audio.
- **pytube**: Alternative plugin for YouTube downloads.

### Steps

1. Clone the repository:
   ```bash
   git clone https://github.com/sohfix/rehab.git
   cd rehab
   ```

2. Create a virtual environment:
   ```bash
   python3 -m venv renv
   ```

3. Activate the virtual environment:
   - **Linux/macOS**:
     ```bash
     source renv/bin/activate
     ```
   - **Windows**:
     ```bash
     renv\Scripts\activate
     ```

4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

5. Run the setup:
   ```bash
   python3 rehab.py setup --linux
   ```
   Replace `--linux` with `--windows` if you're on a Windows system.

---

## Usage

Rehab offers a variety of commands to suit your needs. Below is an overview of the available functionality.

### General Structure

```bash
python3 rehab.py <command> [options]
```

### Commands

#### `setup`
Automate the installation of dependencies and configuration.

- Example:
  ```bash
  python3 rehab.py setup --linux --ini
  ```
  - `--linux`: Installs dependencies for Linux.
  - `--ini`: Walks through and validates the `settings.ini` configuration.

#### `download`
Download audio files from YouTube, RSS feeds, or provided URLs.

- Options:
  - `--youtube`: Provide a YouTube URL to download audio.
  - `--rss`: Specify a podcast RSS feed URL to fetch episodes.
  - `--count`: Limit the number of episodes downloaded from an RSS feed.
  - `--audio-only`: Download only the audio in MP3 format.
  - `--set-title`: Set a custom title for the downloaded content.

- Example:
  ```bash
  python3 rehab.py download --youtube "https://youtu.be/dQw4w9WgXcQ" --audio-only
  ```

#### `record`
Record system audio input.

- Options:
  - `--duration`: Set the duration of the recording (in seconds).
  - `--output`: Specify the output file name.

- Example:
  ```bash
  python3 rehab.py record --duration 60 --output recording.mp3
  ```

---

## Directory Structure

```plaintext
rehab/
│
├── rehab.py          # Main CLI program
├── requirements.txt  # Python dependencies
├── README.md         # Documentation (this file)
├── pylogs/           # Logs for troubleshooting
├── rehab-settings/   # Configuration files
└── renv/             # Virtual environment
```

---

## Contributing

Contributions are welcome! Feel free to submit issues or pull requests on the [GitHub repository](https://github.com/sohfix/rehab).

---

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.

---

## Contact

For any inquiries or feedback, reach out to the author:
- **Email**: [nicolas.tech808@gmail.com](mailto:nicolas.tech808@gmail.com)
- **GitHub**: [github.com/sohfix](https://github.com/sohfix)
