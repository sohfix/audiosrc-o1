# Repository Overview

This repository contains **three Python-based command-line tools**, each serving a distinct purpose:

1. **vrip** – A versatile downloader for podcast RSS feeds and YouTube content, with built-in setup/config commands.
2. **tex2pdf** – A command to compile LaTeX (`.tex`) files into PDF, with progress indication and optional cleanup.
3. **upd** – A utility to copy Python files to a distribution folder, remove the `.py` extension, and make them executable.

Below you’ll find setup instructions, usage examples, and key details for each script.

---

## Table of Contents
- [Requirements](#requirements)
- [Installation](#installation)
- [Script Details](#script-details)
  - [vrip (Audio Downloader)](#vrip-audio-downloader)
  - [tex2pdf (LaTeX Compiler)](#tex2pdf-latex-compiler)
  - [upd (File Distributor)](#upd-file-distributor)
- [License](#license)

---

## Requirements

All scripts require **Python 3**.

Additional Python packages needed:

- **vrip**: `rich`, `requests`, `feedparser`, `pytube` (and/or `yt-dlp`)
- **tex2pdf**: `tqdm`, `termcolor`
- **upd**: Uses the standard library only (`argparse`, `os`, `sys`, `shutil`, `stat`)

Install them with pip, for example:

```bash
pip install rich requests feedparser pytube yt-dlp tqdm termcolor
Installation
Clone or Download this repository.

Install Dependencies

bash
Copy
pip install -r requirements.txt
(Alternatively, install the packages individually as noted above.)

Make Scripts Executable (Optional)
On Linux/macOS, mark the scripts as executable:

bash
Copy
chmod +x vrip.py
chmod +x tex2pdf.py
chmod +x upd.py
Then run them directly (e.g., ./vrip.py).

On Windows, invoke them with:

bash
Copy
python vrip.py
python tex2pdf.py
python upd.py
Script Details
vrip (Audio Downloader)
Usage
bash
Copy
# Show help
python vrip.py --help

# 1) Initialize vrip (auto-detect OS, install dependencies, configure vrip.ini)
python vrip.py init

# 2) Download from a Podcast RSS feed
python vrip.py download --rss https://example.com/podcast/feed.xml --count 3

# 3) Download from YouTube
python vrip.py download --youtube https://youtube.com/watch?v=XYZ --audio-only --use-title

# 4) Setup (manually specify OS, manage configuration)
python vrip.py setup --linux    # Install dependencies on Linux
python vrip.py setup --windows  # Install dependencies on Windows
python vrip.py setup --config   # Create/edit/view vrip.ini

# 5) Read the manual
python vrip.py man
tex2pdf (LaTeX Compiler)
Usage
bash
Copy
# Show help
python tex2pdf.py --help

# Compile a .tex file to PDF in the same directory
python tex2pdf.py main.tex

# Compile a .tex file, placing the PDF in a separate output directory and keeping .aux/.log files
python tex2pdf.py main.tex --output-dir ./build --keep

# Show verbose output (displays pdflatex log)
python tex2pdf.py main.tex --verbose
Options
Option	Description
--output-dir	Directory to save the resulting PDF.
--keep	Keep the .aux and .log files after compilation.
--verbose	Show detailed pdflatex output.
--version	Print the current script version.
upd (File Distributor)
Usage
bash
Copy
# Show help
python upd.py --help

# Copy all .py files from the current directory to $HOME/programs/distribution
python upd.py copy --all

# Copy .py files from a different directory
python upd.py copy -d /path/to/scripts --all

# Interactive selection of .py files to copy from a specified directory
python upd.py copy -d /path/to/scripts
Options
Option/Flag	Description
copy	The action to perform (currently only "copy" is supported).
-d, --dir	Source directory containing .py files (default is .).
--all	Automatically copy all .py files without prompting.
--verbose	Show detailed output for each file copied.
-V, --version	Print the script version.