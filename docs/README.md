# rehab
#### 0.0.11a Version

@author sohfix

# Rehab: Audio Recorder, Splitter, and Downloader

**Rehab** is a powerful command-line tool that helps you **download audio**, **record system input**, and **manage audio files** efficiently. It supports various sources like YouTube, RSS feeds, and more. This project leverages the power of `yt-dlp`, `ffmpeg`, and Python libraries to streamline your audio processing needs.

## Features

- **Download audio** from YouTube, text files, or podcast RSS feeds.
- **Record audio** from system input using `ffmpeg`.
- **Automatic sectioning** when downloading multiple files from text input.
- **Progress bars** and rich console formatting for an intuitive user experience.
- **Comprehensive mini-manual** for quick help and command usage.

---

## Installation

### Prerequisites
Ensure you have the following installed:
- Python 3.8+ (including `pip`)
- `ffmpeg` (for audio recording)
- `yt-dlp` (for audio downloading)

### Steps
1. Clone the repository:
   ```bash
   git clone https://github.com/your-username/rehab.git
   cd rehab

# Create a virtual environment
python3 -m venv renv

# Activate the environment
source renv/bin/activate  # For Linux/macOS
renv\Scripts\activate     # For Windows

# Install dependencies
python3 rehab.py install

rehab/
│
├── rehab.py          # Main CLI program
├── requirements.txt  # Python dependencies
├── README.md         # Documentation (this file)
├── recordings/       # Directory for audio recordings (created on runtime)
└── downloads/        # Directory for downloaded audio (created on runtime)
