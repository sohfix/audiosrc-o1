# CLI Tools Suite: Rehab, Retex, and Twain

![Version](https://img.shields.io/badge/version-1.0.0-green)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

A suite of powerful command-line tools designed for audio processing, LaTeX compilation, and interactive library/journal management. This suite streamlines various workflows with rich visuals, robust features, and seamless integration.

---

## Table of Contents
- [Tools Overview](#tools-overview)
- [Installation](#installation)
  - [Prerequisites](#prerequisites)
  - [Setup](#setup)
- [Usage](#usage)
  - [Rehab](#rehab)
  - [Retex](#retex)
  - [Twain](#twain)
- [Directory Structure](#directory-structure)
- [Contributing](#contributing)
- [License](#license)
- [Contact](#contact)

---

## Tools Overview

### Rehab: Audio Downloader and Processor
Rehab is a robust CLI tool for managing audio files, featuring YouTube downloading, podcast RSS handling, and audio recording.

### Retex: LaTeX to PDF Compiler
Retex provides a streamlined experience for compiling `.tex` files to PDF with progress tracking and auxiliary file management.

### Twain: Library and Journal Manager
Twain is an interactive CLI program for managing a digital library and maintaining a daily journal.

---

## Installation

### Prerequisites

Ensure the following dependencies are installed:
- **Python**: Version 3.8 or higher
- **ffmpeg**: Required for audio processing
- **yt-dlp**: For advanced YouTube downloads
- **pdflatex**: For LaTeX compilation (Retex)

### Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/sohfix/cli-tools-suite.git
   cd cli-tools-suite
Create and activate a virtual environment:

Linux/macOS:
bash
Copy
Edit
python3 -m venv renv
source renv/bin/activate
Windows:
bash
Copy
Edit
python -m venv renv
renv\Scripts\activate
Install dependencies:

bash
Copy
Edit
pip install -r requirements.txt
Usage
Rehab
Rehab offers tools for downloading, managing, and recording audio.

Features:
Download audio from YouTube or podcast RSS feeds.
Record system audio directly.
Automate dependency setup and configuration.
Commands:
Download Audio:
bash
Copy
Edit
python3 rehab.py download --youtube "https://youtu.be/example" --audio-only
Setup:
bash
Copy
Edit
python3 rehab.py setup --linux
Retex
Compile LaTeX .tex files into PDFs with a user-friendly progress bar.

Features:
Visual progress during compilation.
Auxiliary file management (e.g., .aux, .log).
Verbose mode for detailed output.
Commands:
Compile a .tex file:
bash
Copy
Edit
python3 retex.py document.tex -o output/
Twain
Manage your library and daily journal interactively.

Features:
Create and manage digital books with chapters.
Maintain a daily journal for personal use.
Intuitive, interactive menus with rich visuals.
Commands:
Launch Twain:
bash
Copy
Edit
python3 twania.py
Use the menu to:
Add books and chapters.
Edit or delete chapters.
View and manage a daily journal.
Directory Structure
plaintext
Copy
Edit
cli-tools-suite/
│
├── rehab.py         # Rehab CLI tool
├── retex.py         # Retex CLI tool
├── twania.py        # Twain CLI tool
├── requirements.txt # Python dependencies
├── README.md        # Documentation
└── renv/            # Virtual environment
Contributing
Contributions are welcome! Submit issues or pull requests on the GitHub repository.

License
This project is licensed under the MIT License. See the LICENSE file for details.

Contact
For inquiries or feedback, reach out to the author:

Email: nicolas.tech808@gmail.com
GitHub: github.com/sohfix
markdown
Copy
Edit

### Key Details:
- **Full Markdown Syntax**: The document is fully structured and adheres to markdown formatting standards.
- **Sections for Each Tool**: Includes individual descriptions and commands for **Rehab**, **Retex**, and **Twain**.
- **Comprehensive Structure**: Includes installation, usage, directory layout, contributing, and contact information.

Would you like to save this as a new README file or modify specific parts further?
You said:
i need the entire response in markdown. not just some of it. the whole response needs to be in markdown
ChatGPT said:
ChatGPT
markdown
Copy
Edit
# CLI Tools Suite: Rehab, Retex, and Twain

![Version](https://img.shields.io/badge/version-1.0.0-green)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

A suite of powerful command-line tools designed for audio processing, LaTeX compilation, and interactive library/journal management. This suite streamlines various workflows with rich visuals, robust features, and seamless integration.

---

## Table of Contents
- [Tools Overview](#tools-overview)
- [Installation](#installation)
  - [Prerequisites](#prerequisites)
  - [Setup](#setup)
- [Usage](#usage)
  - [Rehab](#rehab)
  - [Retex](#retex)
  - [Twain](#twain)
- [Directory Structure](#directory-structure)
- [Contributing](#contributing)
- [License](#license)
- [Contact](#contact)

---

## Tools Overview

### Rehab: Audio Downloader and Processor
Rehab is a robust CLI tool for managing audio files, featuring YouTube downloading, podcast RSS handling, and audio recording.

### Retex: LaTeX to PDF Compiler
Retex provides a streamlined experience for compiling `.tex` files to PDF with progress tracking and auxiliary file management.

### Twain: Library and Journal Manager
Twain is an interactive CLI program for managing a digital library and maintaining a daily journal.

---

## Installation

### Prerequisites

Ensure the following dependencies are installed:
- **Python**: Version 3.8 or higher
- **ffmpeg**: Required for audio processing
- **yt-dlp**: For advanced YouTube downloads
- **pdflatex**: For LaTeX compilation (Retex)

### Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/sohfix/cli-tools-suite.git
   cd cli-tools-suite
Create and activate a virtual environment:

Linux/macOS:
bash
Copy
Edit
python3 -m venv renv
source renv/bin/activate
Windows:
bash
Copy
Edit
python -m venv renv
renv\Scripts\activate
Install dependencies:

bash
Copy
Edit
pip install -r requirements.txt
Usage
Rehab
Rehab offers tools for downloading, managing, and recording audio.

Features:
Download audio from YouTube or podcast RSS feeds.
Record system audio directly.
Automate dependency setup and configuration.
Commands:
Download Audio:
bash
Copy
Edit
python3 rehab.py download --youtube "https://youtu.be/example" --audio-only
Setup:
bash
Copy
Edit
python3 rehab.py setup --linux
Retex
Compile LaTeX .tex files into PDFs with a user-friendly progress bar.

Features:
Visual progress during compilation.
Auxiliary file management (e.g., .aux, .log).
Verbose mode for detailed output.
Commands:
Compile a .tex file:
bash
Copy
Edit
python3 retex.py document.tex -o output/
Twain
Manage your library and daily journal interactively.

Features:
Create and manage digital books with chapters.
Maintain a daily journal for personal use.
Intuitive, interactive menus with rich visuals.
Commands:
Launch Twain:
bash
Copy
Edit
python3 twania.py
Use the menu to:
Add books and chapters.
Edit or delete chapters.
View and manage a daily journal.
Directory Structure
plaintext
Copy
Edit
cli-tools-suite/
│
├── rehab.py         # Rehab CLI tool
├── retex.py         # Retex CLI tool
├── twania.py        # Twain CLI tool
├── requirements.txt # Python dependencies
├── README.md        # Documentation
└── renv/            # Virtual environment
Contributing
Contributions are welcome! Submit issues or pull requests on the GitHub repository.

License
This project is licensed under the MIT License. See the LICENSE file for details.

Contact
For inquiries or feedback, reach out to the author:

Email: nicolas.tech808@gmail.com
GitHub: github.com/sohfix
