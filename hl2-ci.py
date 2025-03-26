#!/usr/bin/env python3
"""
vrip 3.0.0 [Streamlined + JSON DB + Square-Up Feature]

- Stores basic settings in vrip.ini
- Stores "database" in vrip_db.json to avoid re-downloading
- Provides a 'Square Up Database' menu item to scan your G:\ drive
  and sync the DB with actual files.

Dependencies:
  pip install feedparser requests rich httpx
"""

import configparser
import json
import os
import re
from typing import List, Optional, Tuple

import feedparser
import requests
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

# Global flag to skip SHA256 computation for performance on Windows
SKIP_HASH = True

###############################################################################
#                          FILE PATH CONSTANTS                                #
###############################################################################
CONFIG_PATH = r"C:\vrip_tools\vrip.ini"  # Storing user config
DB_PATH = r"C:\vrip_tools\vrip_db.json"  # JSON DB (podcast file tracking)

###############################################################################
#                          CONFIG & LOGGING SETUP                             #
###############################################################################


def load_config() -> configparser.ConfigParser:
    """Load vrip.ini or create a default if none exists."""
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    config = configparser.ConfigParser()
    if os.path.exists(CONFIG_PATH):
        config.read(CONFIG_PATH)
    else:
        config["Podcasts"] = {"podcast_list": ""}
        with open(CONFIG_PATH, "w") as f:
            config.write(f)
    return config


def parse_podcast_list(config: configparser.ConfigParser) -> List[Tuple[str, str, str]]:
    """
    Return a list of (rss_link, name_id, output_dir) from config's [Podcasts] -> podcast_list.
    Format each entry: RSS_LINK : NAME_ID : OUTPUT_DIRECTORY
    """
    raw = config["Podcasts"].get("podcast_list", "").strip()
    if not raw:
        return []
    chunks = [c.strip() for c in raw.split(";") if c.strip()]
    result = []
    for c in chunks:
        parts = [p.strip() for p in c.split(" : ")]
        if len(parts) == 3:
            rss_link, name_id, out_dir = parts
            result.append((rss_link, name_id, out_dir))
    return result


def write_podcast_list(
    config: configparser.ConfigParser, data: List[Tuple[str, str, str]]
) -> None:
    """
    Write the list of (rss_link, name_id, output_dir) back to config as a semicolon-delimited string.
    """
    parts = [f"{rss} : {name} : {outd}" for (rss, name, outd) in data]
    joined = " ; ".join(parts)
    config["Podcasts"]["podcast_list"] = joined
    with open(CONFIG_PATH, "w") as f:
        config.write(f)


###############################################################################
#                         JSON DATABASE HELPERS                               #
###############################################################################


def load_db() -> dict:
    """Load the JSON DB from DB_PATH, or return a blank structure if not found."""
    if not os.path.exists(DB_PATH):
        return {"podcasts": {}}
    with open(DB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_db(db_data: dict) -> None:
    """Save the DB to DB_PATH as JSON."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(db_data, f, indent=2)


def ensure_podcast_in_db(name_id: str) -> None:
    """Ensure the DB has a 'files' dict for this name_id."""
    db = load_db()
    if "podcasts" not in db:
        db["podcasts"] = {}
    if name_id not in db["podcasts"]:
        db["podcasts"][name_id] = {"files": {}}
    save_db(db)


def file_in_db(name_id: str, file_name: str) -> bool:
    """Check if file_name is recorded in DB for name_id."""
    db = load_db()
    if name_id not in db.get("podcasts", {}):
        return False
    return file_name in db["podcasts"][name_id].get("files", {})


def get_file_info(name_id: str, file_name: str) -> Optional[dict]:
    """Return the file's DB record or None."""
    db = load_db()
    return db["podcasts"].get(name_id, {}).get("files", {}).get(file_name)


def remove_file_from_db(name_id: str, file_name: str) -> None:
    """Remove a file entry from the DB."""
    db = load_db()
    try:
        del db["podcasts"][name_id]["files"][file_name]
        save_db(db)
    except KeyError:
        pass


def update_file_in_db(
    name_id: str, file_name: str, title: str, sha256_val: str, size_val: int
) -> None:
    """Create/update a file entry in DB."""
    db = load_db()
    if "podcasts" not in db:
        db["podcasts"] = {}
    if name_id not in db["podcasts"]:
        db["podcasts"][name_id] = {"files": {}}
    db["podcasts"][name_id]["files"][file_name] = {
        "title": title,
        "sha256": sha256_val,
        "size": size_val,
    }
    save_db(db)


###############################################################################
#                       SCAN & SQUARE-UP DATABASE                             #
###############################################################################


def compute_sha256(file_path: str) -> str:
    """
    Compute SHA256 hash of a file.
    (This function is bypassed if SKIP_HASH is True.)
    """
    import hashlib

    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def square_up_database(drive_path: str = r"G:\\") -> None:
    """
    1) Walk all directories on drive_path
    2) For each .mp3 file, if not in DB, add it.
    3) If DB has files that no longer exist, remove them.
    NOTE: This example lumps files under "unknown_podcast".
    """
    db = load_db()
    if "podcasts" not in db:
        db["podcasts"] = {}

    physically_present = {}
    for root, dirs, files in os.walk(drive_path):
        for fn in files:
            if fn.lower().endswith(".mp3"):
                full_path = os.path.join(root, fn)
                size_val = os.path.getsize(full_path)
                name_id = "unknown_podcast"
                if name_id not in physically_present:
                    physically_present[name_id] = {}
                physically_present[name_id][fn] = {
                    "full_path": full_path,
                    "size": size_val,
                }

    for p_id, data in list(db["podcasts"].items()):
        file_dict = data.get("files", {})
        for fname in list(file_dict.keys()):
            if (p_id not in physically_present) or (
                fname not in physically_present[p_id]
            ):
                remove_file_from_db(p_id, fname)

    for p_id, file_map in physically_present.items():
        ensure_podcast_in_db(p_id)
        for fname, info in file_map.items():
            if not file_in_db(p_id, fname):
                sha_val = "" if SKIP_HASH else compute_sha256(info["full_path"])
                update_file_in_db(
                    p_id, fname, title=fname, sha256_val=sha_val, size_val=info["size"]
                )

    console.print(Panel("Database has been squared up with the drive.", style="green"))


###############################################################################
#                           PODCAST UPDATE LOGIC                              #
###############################################################################


def already_have_file(
    name_id: str, file_name: str, expected_size: Optional[int]
) -> bool:
    """
    Return True if we can skip download.
    """
    if not file_in_db(name_id, file_name):
        return False
    info = get_file_info(name_id, file_name)
    if expected_size and info.get("size", 0) < expected_size:
        return False
    return True


def download_file(url: str, dest: str) -> bool:
    """Download a file from url to dest. Returns True if success."""
    try:
        r = requests.get(url, stream=True, timeout=15)
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        return True
    except Exception as e:
        console.print(Panel(f"Error downloading {url}\n{e}", style="red"))
        return False


def update_podcast(name_id: str, rss_link: str, out_dir: str) -> None:
    """
    Parse the feed and update episodes:
      1) Build a local filename.
      2) Check DB; skip if already present.
      3) Else download and update DB.
    """
    console.print(Panel(f"Updating '{name_id}' => {rss_link}", style="cyan"))
    os.makedirs(out_dir, exist_ok=True)
    ensure_podcast_in_db(name_id)

    feed = feedparser.parse(rss_link)
    if not feed.entries:
        console.print(Panel("No entries found in RSS feed.", style="yellow"))
        return

    count_total = len(feed.entries)
    count_done = 0
    for entry in feed.entries:
        if not entry.enclosures or not entry.enclosures[0].href:
            continue
        url = entry.enclosures[0].href
        title = entry.title
        try:
            expected_len = int(entry.enclosures[0].get("length", 0))
        except:
            expected_len = None

        base_name = re.sub(r"[^\w\s-]", "", title).strip()
        file_name = base_name + ".mp3"
        dest_path = os.path.join(out_dir, file_name)

        if already_have_file(name_id, file_name, expected_len):
            console.print(f"[SKIP] {file_name} (already in DB)")
            continue

        if os.path.exists(dest_path):
            file_size = os.path.getsize(dest_path)
            if expected_len and file_size < expected_len:
                console.print(f"[RE-DOWNLOAD] {file_name} seems incomplete.")
                os.remove(dest_path)
            else:
                hval = "" if SKIP_HASH else compute_sha256(dest_path)
                update_file_in_db(name_id, file_name, title, hval, file_size)
                console.print(f"[DB-ADD] Found {file_name} on disk; DB updated.")
                continue

        console.print(Panel(f"Downloading: {file_name}", style="blue"))
        success = download_file(url, dest_path)
        if success:
            fsize = os.path.getsize(dest_path)
            sha_val = "" if SKIP_HASH else compute_sha256(dest_path)
            update_file_in_db(name_id, file_name, title, sha_val, fsize)
            console.print(Panel(f"Downloaded: {file_name}", style="green"))
        else:
            console.print(Panel(f"Failed to download {file_name}", style="red"))

        count_done += 1

    console.print(
        Panel(
            f"Update complete for '{name_id}'. {count_done} new/updated files out of {count_total} feed entries.",
            style="green",
        )
    )


###############################################################################
#                            INTERACTIVE MENUS                                #
###############################################################################


def menu_download():
    """
    Allows you to pick from stored podcasts or enter a custom RSS link.
    """
    config = load_config()
    while True:
        console.print(
            Panel(
                "Download Menu\n\n1) Choose from stored podcasts\n2) Enter custom RSS link\n3) Return to main menu",
                title="Download",
                style="cyan",
            )
        )
        choice = console.input("Enter choice: ").strip()
        if choice == "1":
            plist = parse_podcast_list(config)
            if not plist:
                console.print(
                    Panel("No stored podcasts found. Add them first.", style="yellow")
                )
                continue
            table = Table(title="Stored Podcasts")
            table.add_column("NAME_ID")
            table.add_column("RSS Link")
            table.add_column("Output Dir")
            for rss, nid, outd in plist:
                table.add_row(nid, rss, outd)
            console.print(table)

            pick = console.input("Enter the NAME_ID to download: ").strip()
            matches = [p for p in plist if p[1].lower() == pick.lower()]
            if not matches:
                console.print(Panel(f"No match for '{pick}'", style="red"))
                continue
            chosen_rss, chosen_id, chosen_out = matches[0]
            update_podcast(chosen_id, chosen_rss, chosen_out)

        elif choice == "2":
            custom_rss = console.input("Enter custom RSS link: ").strip()
            if not custom_rss:
                console.print("No link entered.")
                continue
            out_dir = console.input("Enter output directory (e.g. G:\\MyPod): ").strip()
            name_id = (
                console.input("Name this feed (any short ID): ").strip() or "custom"
            )
            update_podcast(name_id, custom_rss, out_dir)
        elif choice == "3":
            break
        else:
            console.print(Panel("Invalid choice", style="red"))


def menu_update():
    """
    Allows you to update podcasts or square up the DB.
    """
    config = load_config()
    while True:
        console.print(
            Panel(
                "Update Menu\n\n1) Update All Podcasts\n2) Update One Podcast\n3) Square Up Database\n4) Return to main menu",
                title="Update",
                style="magenta",
            )
        )
        choice = console.input("Enter choice: ").strip()
        if choice == "1":
            plist = parse_podcast_list(config)
            if not plist:
                console.print(Panel("No stored podcasts found.", style="yellow"))
                continue
            for rss, nid, outd in plist:
                update_podcast(nid, rss, outd)

        elif choice == "2":
            plist = parse_podcast_list(config)
            if not plist:
                console.print(Panel("No stored podcasts found.", style="yellow"))
                continue
            table = Table(title="Stored Podcasts")
            table.add_column("NAME_ID")
            table.add_column("RSS Link")
            table.add_column("Output Dir")
            for rss, nid, outd in plist:
                table.add_row(nid, rss, outd)
            console.print(table)
            pick = console.input("Enter the NAME_ID to update: ").strip()
            matches = [p for p in plist if p[1].lower() == pick.lower()]
            if not matches:
                console.print(Panel(f"No match for '{pick}'", style="red"))
                continue
            chosen_rss, chosen_id, chosen_out = matches[0]
            update_podcast(chosen_id, chosen_rss, chosen_out)

        elif choice == "3":
            drive_path = console.input(
                "Enter drive/folder to scan (default=G:\\): "
            ).strip()
            if not drive_path:
                drive_path = r"G:\\"
            square_up_database(drive_path)
        elif choice == "4":
            break
        else:
            console.print(Panel("Invalid choice", style="red"))


def menu_settings():
    """
    Edit or view config & manage the stored podcast list.
    """
    config = load_config()
    while True:
        console.print(
            Panel(
                "Settings Menu\n\n1) View config\n2) Manage podcasts list\n3) Return to main menu",
                title="Settings",
                style="cyan",
            )
        )
        choice = console.input("Enter choice: ").strip()
        if choice == "1":
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    content = f.read()
                console.print(Panel(content, title="vrip.ini", style="blue"))
            else:
                console.print(Panel("No config file found.", style="red"))
        elif choice == "2":
            while True:
                plist = parse_podcast_list(config)
                console.print(
                    Panel(
                        "Podcast List Mgmt\n\n1) View list\n2) Add new\n3) Remove\n4) Return",
                        style="cyan",
                    )
                )
                c2 = console.input("Enter choice: ").strip()
                if c2 == "1":
                    if not plist:
                        console.print("No podcasts stored.")
                    else:
                        t = Table(title="Podcasts")
                        t.add_column("RSS Link")
                        t.add_column("NAME_ID")
                        t.add_column("Output Dir")
                        for rss, nid, outd in plist:
                            t.add_row(rss, nid, outd)
                        console.print(t)
                elif c2 == "2":
                    new_line = console.input(
                        "Enter new (RSS_LINK : NAME_ID : OUTPUT_DIR): "
                    ).strip()
                    parts = [p.strip() for p in new_line.split(" : ")]
                    if len(parts) == 3:
                        rss, nameid, outd = parts
                        new_plist = plist[:]
                        new_plist.append((rss, nameid, outd))
                        write_podcast_list(config, new_plist)
                        console.print("Added.")
                    else:
                        console.print("Invalid format.")
                elif c2 == "3":
                    if not plist:
                        console.print("No podcasts to remove.")
                        continue
                    for idx, (rss, nid, outd) in enumerate(plist, start=1):
                        console.print(f"{idx}) {nid} -> {rss} ({outd})")
                    rm_idx_str = console.input("Which # to remove? ").strip()
                    try:
                        rm_idx = int(rm_idx_str)
                        if 1 <= rm_idx <= len(plist):
                            removed = plist.pop(rm_idx - 1)
                            write_podcast_list(config, plist)
                            console.print(f"Removed {removed[1]}")
                        else:
                            console.print("Invalid selection.")
                    except:
                        console.print("Not a valid number.")
                elif c2 == "4":
                    break
                else:
                    console.print("Invalid choice.")
        elif choice == "3":
            break
        else:
            console.print(Panel("Invalid choice", style="red"))


def menu_manual_about():
    """
    Show manual & about.
    """
    while True:
        console.print(
            Panel(
                "Manual & About\n\n1) Show manual\n2) About\n3) Return to main menu",
                style="cyan",
            )
        )
        choice = console.input("Enter choice: ").strip()
        if choice == "1":
            manual = """
[bold]vrip 3.0.0 - Streamlined + JSON DB + Square-Up[/bold]

This tool downloads & updates podcasts from RSS feeds. 
It uses:
- [blue]vrip.ini[/blue] to store your stored feeds & settings
- [blue]vrip_db.json[/blue] as a "database" so files don't get redownloaded.

Features:
  - Basic scanning & verifying of files on disk.
  - "Square up" your G:\\ (or any folder) to fix DB mismatches.
  - Minimal re-downloading.

Enjoy!
"""
            console.print(manual)
        elif choice == "2":
            console.print(Panel("vrip 3.0.0\nAuthor: You\n", style="green"))
        elif choice == "3":
            break
        else:
            console.print(Panel("Invalid choice", style="red"))


###############################################################################
#                                     MAIN                                    #
###############################################################################


def main():
    banner = "========== Welcome to vrip (3.0.0) =========="
    console.print(Panel(banner, style="magenta"))
    while True:
        console.print(
            Panel(
                "Main Menu\n\n1) Download Podcasts\n2) Update Podcasts\n3) Settings\n4) Manual & About\n5) Exit",
                title="vrip",
                style="magenta",
            )
        )
        choice = console.input("Enter choice: ").strip()
        if choice == "1":
            menu_download()
        elif choice == "2":
            menu_update()
        elif choice == "3":
            menu_settings()
        elif choice == "4":
            menu_manual_about()
        elif choice == "5":
            console.print(Panel("Exiting... Thanks!", style="magenta"))
            break
        else:
            console.print(Panel("Invalid choice.", style="red"))


if __name__ == "__main__":
    main()
