import json
import sqlite3
import os
import random
from rich.console import Console
from rich.table import Table

# glo
# === GLOBALS & INITIALIZATION ===
console = Console()

DB_FILE = "hitchhiker_game.db"
BOOKS_DIR = "books"  # Directory containing multiple JSON book files


# === DATABASE SETUP ===
def setup_database():
    """Creates all required tables if they don't exist."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Players Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            chosen_book TEXT,                      -- Store the chosen book filename
            money INTEGER DEFAULT 50,
            miles_remaining INTEGER DEFAULT 200,
            location TEXT DEFAULT 'Highway Start',
            backpack_size INTEGER DEFAULT 10,
            health INTEGER DEFAULT 100,
            reputation INTEGER DEFAULT 0
        )
    """)

    # Story Fragments (for each user)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS story_fragments (
            fragment_id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER,
            order_number INTEGER,
            text TEXT,
            is_unlocked BOOLEAN DEFAULT 0,
            FOREIGN KEY(player_id) REFERENCES players(id)
        )
    """)

    # Inventory Table (general items)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            player_id INTEGER,
            item_name TEXT,
            quantity INTEGER DEFAULT 1,
            category TEXT,
            durability INTEGER DEFAULT 100,
            FOREIGN KEY(player_id) REFERENCES players(id)
        )
    """)

    # Weapons Table (belt inventory)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS weapons (
            player_id INTEGER,
            slot INTEGER,
            weapon_name TEXT,
            type TEXT,
            damage INTEGER DEFAULT 10,
            ammo INTEGER DEFAULT 0,
            condition INTEGER DEFAULT 100,
            FOREIGN KEY(player_id) REFERENCES players(id)
        )
    """)

    # Jobs Table (tracks player's job skills)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            player_id INTEGER,
            job_type TEXT,
            skill_level INTEGER DEFAULT 1,
            skill_exp INTEGER DEFAULT 0,
            FOREIGN KEY(player_id) REFERENCES players(id)
        )
    """)

    # Encounters Table (record of hitchhike events)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS encounters (
            player_id INTEGER,
            driver_name TEXT,
            driver_type TEXT,
            result TEXT,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(player_id) REFERENCES players(id)
        )
    """)

    conn.commit()
    conn.close()


# === BOOK SELECTION & INSERTION ===
def list_available_books():
    """
    Lists all .json files in the BOOKS_DIR folder.
    Returns a list of filenames (without path).
    """
    if not os.path.exists(BOOKS_DIR):
        return []
    files = os.listdir(BOOKS_DIR)
    return [f for f in files if f.lower().endswith(".json")]


def load_book(book_filename):
    """
    Loads the given book JSON from the books/ directory.
    Structure:
    {
      'title': str,
      'author': str,
      'chapters': [
          { 'order': int, 'text': str }
      ]
    }
    """
    full_path = os.path.join(BOOKS_DIR, book_filename)
    if not os.path.exists(full_path):
        console.print(f"[bold red]ERROR: Book file {book_filename} not found in {BOOKS_DIR}![/bold red]")
        return None
    with open(full_path, "r") as file:
        return json.load(file)


def initialize_player_fragments(player_id, book_filename):
    """
    Inserts locked story fragments for the given player and chosen book
    (only if they don't already exist).
    """
    book_data = load_book(book_filename)
    if not book_data:
        return  # Book file missing or invalid

    chapters = book_data.get("chapters", [])
    if not chapters:
        console.print("[bold red]ERROR: Book has no chapters![/bold red]")
        return

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    for c in chapters:
        order_number = c["order"]
        text = c["text"]

        cursor.execute("""
            SELECT 1 FROM story_fragments
            WHERE player_id = ? AND order_number = ?
        """, (player_id, order_number))
        exists = cursor.fetchone()

        if not exists:
            cursor.execute("""
                INSERT INTO story_fragments (player_id, order_number, text, is_unlocked)
                VALUES (?, ?, ?, 0)
            """, (player_id, order_number, text))

    conn.commit()
    conn.close()


# === CORE STORY FUNCTIONS ===
def unlock_next_fragment(player_id):
    """
    Unlocks the next locked fragment in sequence, if the previous is unlocked.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Check the highest order_number that is unlocked
    cursor.execute("""
        SELECT MAX(order_number)
        FROM story_fragments
        WHERE player_id = ? AND is_unlocked = 1
    """, (player_id,))
    result = cursor.fetchone()
    highest_unlocked = result[0] if result and result[0] else 0

    # Next fragment to unlock
    next_to_unlock = highest_unlocked + 1

    # See if that fragment exists & is locked
    cursor.execute("""
        SELECT fragment_id FROM story_fragments
        WHERE player_id = ? AND order_number = ? AND is_unlocked = 0
    """, (player_id, next_to_unlock))
    row = cursor.fetchone()

    if row:
        cursor.execute("""
            UPDATE story_fragments
            SET is_unlocked = 1
            WHERE fragment_id = ?
        """, (row[0],))
        console.print(f"[bold green]You unlocked chapter {next_to_unlock}![/bold green]")
    else:
        console.print("[bold yellow]No further fragments to unlock or it's already unlocked.[/bold yellow]")

    conn.commit()
    conn.close()


def get_player_id(username):
    """
    Retrieves the player's ID.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM players WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def get_player_book(username):
    """
    Returns the chosen_book filename for a user.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT chosen_book FROM players WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def get_unlocked_fragments(player_id):
    """
    Returns a list of (order_number, text) for all unlocked fragments.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT order_number, text
        FROM story_fragments
        WHERE player_id = ? AND is_unlocked = 1
        ORDER BY order_number ASC
    """, (player_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_locked_fragments(player_id):
    """
    Returns a list of order_numbers for all locked fragments.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT order_number
        FROM story_fragments
        WHERE player_id = ? AND is_unlocked = 0
        ORDER BY order_number ASC
    """, (player_id,))
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows]


# === PLAYER AUTH ===
def register_player(username, password, chosen_book):
    """
    Register a new player with the selected book.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO players (username, password, chosen_book)
            VALUES (?, ?, ?)
        """, (username, password, chosen_book))
        conn.commit()

        # Get new player's ID
        cursor.execute("SELECT id FROM players WHERE username = ?", (username,))
        player_id = cursor.fetchone()[0]
        conn.close()

        # Initialize locked fragments for that player from chosen book
        initialize_player_fragments(player_id, chosen_book)

        return f"✅ Player '{username}' registered successfully with book '{chosen_book}'!"
    except sqlite3.IntegrityError:
        conn.close()
        return "❌ Username already exists. Please choose another."


def login_player(username, password):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM players WHERE username = ? AND password = ?", (username, password))
    player = cursor.fetchone()
    conn.close()
    return player is not None


# === GAME MENUS ===
def main_menu():
    while True:
        console.clear()
        console.print("[bold cyan]🏜️ Hitchhiker Mystery Game[/bold cyan]")
        console.print("[bold]1.[/bold] New Game")
        console.print("[bold]2.[/bold] Load Game")
        console.print("[bold]3.[/bold] Quit")
        choice = input("\nChoose an option: ")
        if choice == "1":
            new_game()
        elif choice == "2":
            load_game()
        elif choice == "3":
            console.print("[bold red]Exiting game...[/bold red]")
            break


def new_game():
    console.clear()
    console.print("[bold green]🆕 New Game Setup[/bold green]")

    # 1) Pick Username & Password
    username = input("Enter a new username: ")
    password = input("Enter a password: ")

    # 2) List available books
    books = list_available_books()
    if not books:
        console.print("[bold red]No .json book files found in 'books' directory![/bold red]")
        console.print("Please add your book JSON files and restart.")
        return

    console.print("\nAvailable Books in 'books' folder:")
    for i, bk in enumerate(books, 1):
        console.print(f"[bold]{i}.[/bold] {bk}")

    # 3) Choose book
    while True:
        choice = input("\nChoose a book by number: ")
        if not choice.isdigit():
            console.print("[red]Please enter a valid number.[/red]")
            continue
        choice_idx = int(choice) - 1
        if 0 <= choice_idx < len(books):
            chosen_book = books[choice_idx]
            break
        else:
            console.print("[red]Invalid selection, try again.[/red]")

    # 4) Register Player
    result = register_player(username, password, chosen_book)
    console.print(result)

    # If registration is successful, start game
    if "successfully" in result:
        start_game(username)


def load_game():
    console.clear()
    console.print("[bold blue]🔄 Load Existing Game[/bold blue]")
    username = input("Enter your username: ")
    password = input("Enter your password: ")

    if login_player(username, password):
        start_game(username)
    else:
        console.print("❌ Invalid username or password. Please try again.")


# === CORE GAME LOOP ===
def start_game(username):
    player_id = get_player_id(username)
    chosen_book = get_player_book(username)

    console.print(f"\n[bold cyan]🌅 {username}, you've loaded the book: [yellow]{chosen_book}[/yellow][/bold cyan]")
    console.print("Cars pass by; your journey awaits...")

    while True:
        console.print("\n[bold]🚗 What do you do?[/bold]")
        console.print("[1] Flag down a car")
        console.print("[2] Check your inventory")
        console.print("[3] Look for a job")
        console.print("[4] View story fragments (Corkboard & Timeline)")
        console.print("[5] Unlock next fragment manually (cheat command)")
        console.print("[6] Quit to Main Menu")

        choice = input("Choose an action: ")
        if choice == "1":
            hitchhike_event(player_id)
        elif choice == "2":
            show_inventory(player_id)
        elif choice == "3":
            find_job(player_id)
        elif choice == "4":
            view_story_fragments(player_id)
        elif choice == "5":
            unlock_next_fragment(player_id)
        elif choice == "6":
            break


# === HITCHHIKING SYSTEM ===
def hitchhike_event(player_id):
    # Random driver archetypes
    drivers = [
        {"name": "Tex", "type": "Friendly"},
        {"name": "Linda", "type": "Weird"},
        {"name": "Sam", "type": "Rude"},
        {"name": "Mysterious Stranger", "type": "Dangerous"}
    ]
    driver = random.choice(drivers)

    console.print("\n[bold yellow]🚗 A car pulls up...[/bold yellow]")
    console.print(f"[bold]{driver['name']}[/bold] is a {driver['type'].lower()} driver.")

    console.print("\n[1] Accept the ride")
    console.print("[2] Ask about their destination")
    console.print("[3] Decline the ride")

    choice = input("Choose an action: ")
    if choice == "1":
        console.print("[bold green]🚙 You hop in the car. They drive you a few miles down the road...[/bold green]")
        update_miles(player_id, random.randint(5, 30))
    elif choice == "2":
        console.print("[bold blue]🗺️ The driver vaguely describes a far-off place...[/bold blue]")
    elif choice == "3":
        console.print("[bold red]🚶‍♂️ You decide to wait for another ride.[/bold red]")


def update_miles(player_id, miles):
    """Subtract miles from player's total. If 0, they've reached their destination."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT miles_remaining FROM players WHERE id = ?", (player_id,))
    current = cursor.fetchone()[0]
    new_value = current - miles
    if new_value < 0:
        new_value = 0
    cursor.execute("UPDATE players SET miles_remaining = ? WHERE id = ?", (new_value, player_id))
    conn.commit()
    conn.close()
    console.print(f"[bold magenta]You've traveled {miles} miles. Remaining: {new_value}[/bold magenta]")
    if new_value <= 0:
        console.print("[bold green]🎉 You've reached your final destination![/bold green]")


# === INVENTORY SYSTEM (Simplified) ===
def show_inventory(player_id):
    console.print(f"\n[bold yellow]🎒 Inventory[/bold yellow]")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT item_name, quantity, category, durability
        FROM inventory
        WHERE player_id = ?
    """, (player_id,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        console.print("Your backpack is empty.")
        return

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Item Name")
    table.add_column("Quantity")
    table.add_column("Category")
    table.add_column("Durability")

    for r in rows:
        table.add_row(str(r[0]), str(r[1]), str(r[2]), str(r[3]))

    console.print(table)


# === JOB SYSTEM (Simplified) ===
def find_job(player_id):
    console.print("\n[bold green]💼 Searching for temporary work...[/bold green]")
    jobs = [
        {"job_type": "Cooking", "base_pay": 20},
        {"job_type": "Repair", "base_pay": 30},
        {"job_type": "General", "base_pay": 10}
    ]
    job = random.choice(jobs)

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT skill_level, skill_exp FROM jobs
        WHERE player_id = ? AND job_type = ?
    """, (player_id, job["job_type"]))
    record = cursor.fetchone()

    if record:
        skill_level, skill_exp = record
    else:
        # Insert a new record with default skill/exp
        cursor.execute("""
            INSERT INTO jobs (player_id, job_type, skill_level, skill_exp)
            VALUES (?, ?, 1, 0)
        """, (player_id, job["job_type"]))
        conn.commit()
        skill_level, skill_exp = 1, 0

    console.print(f"You found a [bold]{job['job_type']}[/bold] job offering base pay of ${job['base_pay']}.")

    # Calculate pay based on skill_level
    final_pay = job["base_pay"] + (skill_level * 5)
    console.print(f"[bold yellow]You earned ${final_pay} for this job![/bold yellow]")

    # Update player's money
    cursor.execute("SELECT money FROM players WHERE id = ?", (player_id,))
    current_money = cursor.fetchone()[0]
    new_money = current_money + final_pay
    cursor.execute("UPDATE players SET money = ? WHERE id = ?", (new_money, player_id))

    # Increase skill_exp
    skill_exp += 10
    if skill_exp >= 50:
        skill_level += 1
        skill_exp = 0
        console.print("[bold green]Your skill level increased![/bold green]")

    # Update DB
    cursor.execute("""
        UPDATE jobs
        SET skill_level = ?, skill_exp = ?
        WHERE player_id = ? AND job_type = ?
    """, (skill_level, skill_exp, player_id, job["job_type"]))

    conn.commit()
    conn.close()


# === STORY FRAGMENTS: CORKBOARD & TIMELINE ===
def view_story_fragments(player_id):
    unlocked = get_unlocked_fragments(player_id)
    locked = get_locked_fragments(player_id)

    # Corkboard
    console.print("\n[bold blue]📌 CORKBOARD - STORY FRAGMENTS[/bold blue]")
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Chapter #")
    table.add_column("Status")
    table.add_column("Snippet")

    for (order_num, text) in unlocked:
        snippet = text[:50] + ("..." if len(text) > 50 else "")
        table.add_row(str(order_num), "[green]Unlocked[/green]", snippet)

    for order_num in locked:
        table.add_row(str(order_num), "[red]Locked[/red]", "???")

    console.print(table)

    # Timeline
    console.print("\n[bold yellow]📅 TIMELINE[/bold yellow]")
    # highest unlocked
    highest_unlocked = unlocked[-1][0] if unlocked else 0

    # find max chapter
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT MAX(order_number) FROM story_fragments
        WHERE player_id = ?
    """, (player_id,))
    max_chapter = cursor.fetchone()[0]
    conn.close()

    if not max_chapter:
        console.print("No fragments found. Possibly no chapters loaded.")
        return

    timeline_str = ""
    for chap in range(1, max_chapter + 1):
        if chap <= highest_unlocked:
            timeline_str += f"[{chap}=Unlocked]--"
        elif chap in locked:
            timeline_str += f"[{chap}=Locked]--"
        else:
            # edge case if there's a gap
            timeline_str += f"[{chap}=Locked]--"

    timeline_str = timeline_str.strip("-")
    console.print(timeline_str)


# === ENTRY POINT ===
def main():
    setup_database()
    # No default config needed, but we can expand if needed
    main_menu()

if __name__ == "__main__":
    main()
