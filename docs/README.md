# prx 2.1.0

G:\-Only Edition with Damaged File Checking (5MB Tolerance)

---

## Overview

prx is a command-line (CLI) podcast downloader. It uses an INI file on your G: drive for configuration – storing both system settings and a list of podcasts. It can:

1. Download RSS-based podcast episodes.
2. Update (batch-download) any missing or damaged episodes.
3. Skip episodes already on disk.
4. Check for Damaged Files using a 5MB Tolerance in comparing file sizes.

---

## Features

- **G:\-Only**:
  All references (config, downloads, logs) use G:\ – no OS detection or special handling.

- **Rich CLI Interface**:
  Uses Rich for colorful output, progress bars, tables, etc.

- **Damaged File Checking**:
  - If local file size is > 5MB smaller than the remote size (taken from feed or HTTP HEAD), we remove and re-download it.
  - If the remote size is unknown or the discrepancy is less than 5MB, we treat the file as good and skip re-downloading.

- **Automatic Sorting & Searching**:
  - Sort episodes by their published/updated date, either oldest-first or newest-first.
  - Optional “search term” to only download episodes whose titles match a string.

- **Quiet Mode, Verbose Mode**:
  - Quiet: Minimizes console output (toggle by QUIET_MODE global or INI setting).
  - Verbose: Shows extended server info, final download speeds, etc.

- **Retries & Exponential Backoff**:
  If a download fails or times out, prx tries again with a bigger delay each time (up to a configurable max).

---

## Installation & Setup

1. **Place prx.py on G:\\**
   Make sure Python is installed on your system. Then copy prx.py (and the entire script) to G:\.

2. **Initial Run**
   Open a command prompt or PowerShell, navigate to G:\, and run:
python prx.py

markdown
Copy
Edit
The app will look for `G:\tools\prx.ini`. If not found, it creates a default one. You’ll be prompted for basic config like name and password.

3. **Dependencies**
- requests
- feedparser
- httpx
- rich

Install them if needed:
pip install requests feedparser httpx rich

sql
Copy
Edit

4. **Check/Update prx.ini**
After the first run, prx.ini is located at:
G:\tools\prx.ini

yaml
Copy
Edit
You can edit it to change:
- default_output_dir (download directory for custom RSS’s)
- download_timeout, max_retries, etc.
- podcast_list (the main list of stored podcasts).

---

## Configuration: prx.ini

A typical prx.ini on G:\tools might look like:

[user] name = MyName password = secret123

[system] os = windows default_output_dir = G:\tools\downloads download_timeout = 10 max_retries = 3 initial_retry_backoff = 2 https_only = False quiet_mode = False

[logging] log_dir = G:\tools\logs log_level = INFO

[Podcasts] podcast_list = https://somefeed.com/feed.xml : MyShow : G:\tools\downloads ; https://otherfeed.xyz/pod.rss : AnotherShow : G:\tools\podcasts

python
Copy
Edit

### [Podcasts] section

- `podcast_list` is a semicolon-separated list of items with the format:
PODCAST_LINK : NAME_ID : OUTPUT_DIRECTORY

makefile
Copy
Edit
Example:
https://myfeed.com/rss : MyFeed : G:\podcasts\myfeed ; https://rss.another.com/coolshow.xml : AnotherCoolShow : G:\podcasts\another

yaml
Copy
Edit

---

## Usage

Launch prx with:
python G:\prx.py

css
Copy
Edit
You’ll see a Main Menu:

Main Menu

Download Podcasts

Update Podcasts

Settings

About

Exit

sql
Copy
Edit

### 1) Download Podcasts
- Choose from Stored (by NAME_ID) or Enter Custom RSS URL.
- You can optionally specify:
  - Oldest first? (y/n)
  - How many episodes to download.
  - A search term to filter episodes by title.
  - Enable logging (writes to G:\tools\logs).
  - Verbose output for extended server info and speed.

Any local file that already exists and is not considered damaged is skipped.

### 2) Update Podcasts
- Update All:
  Goes through every podcast in [Podcasts] -> podcast_list, checks each feed, and downloads missing or damaged episodes.
- Update One:
  Lets you select from the stored NAME_IDs. Then does the same “missing or damaged episodes” logic.

### 3) Settings
- Init: Creates/loads prx.ini, asks for name & password if missing.
- Manage Config: View or edit the raw prx.ini.
- Manage Podcasts List: Interactive menu to add, edit, or remove feed entries from podcast_list.

### 4) About
- Shows the version and a short summary.

### 5) Exit
- Quits the program.

---

## Damaged File Checking

By default, prx uses the is_file_damaged() function with a 5MB tolerance:

1. If your local file doesn’t exist, it’s “damaged” => prx will download.
2. If the feed provides a valid enclosure length (and it’s > 0), we use that as remote_size.
3. If that’s missing, prx does a HEAD request on the MP3 to see Content-Length.
4. If we still can’t find a valid remote size, we assume the file is okay (no redownload).
5. We compare (remote_size - local_size). If it’s more than 5 MB, we call it incomplete => prx deletes local and re-downloads.

### Changing the tolerance
Inside the code, look for:
TOLERANCE = 5 * 1024 * 1024

---

## Troubleshooting

1. **False positives** if the feed lists the wrong size.
   - Increase the TOLERANCE or set https_only = False to skip HEAD if the server is also inaccurate.
   - If the feed is consistently lying about sizes, you might want to disable the damaged-file logic.

2. **Timeouts** on slow servers.
   - Increase download_timeout in prx.ini.
   - The app also tries exponential backoff up to max_retries.

3. **No episodes found** in an RSS feed.
   - Check the feed URL is correct.
   - Some feeds require authentication or special tokens. In such a scenario, prx might not handle it out of the box.

4. **Feed shows length="0"** for every episode.
   - prx attempts a HEAD request. If that also fails or returns 0, prx will skip the damaged-file logic and treat the file as good.

---

## Logging

By default, prx writes logs to:
G:\tools\logs\session_YYYYMMDD_HHMMSS.log

yaml
Copy
Edit
Unless log_dir is empty or does not exist.

Log Level can be DEBUG, INFO, WARNING, ERROR, CRITICAL.

---

## Example Workflows

### Quick Start
1. **Add a feed**:
   - Run prx.
   - Go to Settings -> Manage podcasts -> Add new.
   - Enter something like:
     ```
     https://example.com/podcast.rss : MyShow : G:\myshows\MyShow
     ```

2. **Download episodes**:
   - Main Menu -> Download -> From stored podcast list.
   - Pick MyShow, specify oldest first, or how many episodes, etc.
   - If the file is present and big enough (within 5MB of the feed’s reported size), prx will skip it. Otherwise, it downloads.

### Updating an Entire Library
- Main Menu -> Update Podcasts -> Update All
- prx scans each feed in [Podcasts] and re-downloads only those episodes that are missing or definitely incomplete by more than 5MB.

---

## Contact / License

- **Author**: sohfix
- **License**: MIT

For bug reports or suggestions, contact the developer or open an issue on your private repository (if you have one).







