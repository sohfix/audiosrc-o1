#!/home/sohfix/PycharmProjects/rehab/renv/bin/python3

import json
import os
import time
from datetime import date
from rich.console import Console
from rich.table import Table
from rich.progress import Progress
from rich.prompt import Prompt
from rich.text import Text
from time import sleep
import sys

# VERSION
VERSION = "1.0.0"

# Rich Console
console = Console()

# Library and journal data storage
library = {}
journal = {}

# Utility to clear the screen
def clear_screen():
    console.clear()

def close_term():
    console.print("\n[red]Exiting...[reset]")
    sys.exit(0)


# Display banner
def display_banner():
    banner = Text()
    banner.append("\n", style="bold blue")
    banner.append(" _______                  _       \n", style="bold cyan")
    banner.append("|__   __|                (_)      \n", style="bold cyan")
    banner.append("   | |_      ____ _ _ __  _  __ _ \n", style="bold green")
    banner.append("   | \\ \\ /\\ / / _` | '_ \\| |/ _` |\n", style="bold green")
    banner.append("   | |\\ V  V / (_| | | | | | (_| |\n", style="bold yellow")
    banner.append("   |_| \\_/\\_/ \\__,_|_| |_|_|\\__,_|\n", style="bold yellow")
    banner.append("\n", style="bold blue")
    banner.append("=== A CLI Library & Journal ===\n", style="bold magenta")
    banner.append(f"=== Version {VERSION} ===\n", style="bold white")

    console.print(banner)

# Load data from files
def load_data():
    global library, journal
    with Progress() as progress:
        task = progress.add_task("[cyan]Loading data...", total=2)
        sleep(0.5)
        if os.path.exists("library.json"):
            with open("library.json", "r") as file:
                library.update(json.load(file))
        progress.advance(task)
        sleep(0.5)
        if os.path.exists("journal.json"):
            with open("journal.json", "r") as file:
                journal.update(json.load(file))
        progress.advance(task)
        sleep(0.5)

# Save data to files
def save_data():
    with Progress() as progress:
        task = progress.add_task("[green]Saving data...", total=2)
        sleep(0.5)
        with open("library.json", "w") as file:
            json.dump(library, file)
        progress.advance(task)
        sleep(0.5)
        with open("journal.json", "w") as file:
            json.dump(journal, file)
        progress.advance(task)
        sleep(0.5)
    console.print(":white_check_mark: [green]Data saved successfully![/green]")

# Main menu
def main_menu():
    while True:
        clear_screen()
        display_banner()
        console.print("1. 📚 Library")
        console.print("2. 📝 Daily Journal")
        console.print("3. 💾 Save and Exit")
        choice = Prompt.ask("Choose an option", choices=["1", "2", "3"], default="3")

        if choice == "1":
            library_menu()
        elif choice == "2":
            journal_menu()
        elif choice == "3":
            save_data()
            console.print(":wave: [yellow]Goodbye![/yellow]")
            break

# Library menu
def library_menu():
    while True:
        clear_screen()
        console.print("[bold blue]=== Library ===[/bold blue]")
        console.print("1. ➕ Add Book")
        console.print("2. ✏️ Edit Book")
        console.print("3. 🗑️ Delete Book")
        console.print("4. 📖 View Book")
        console.print("5. 📚 List Books")
        console.print("6. 🔙 Back to Main Menu")
        choice = Prompt.ask("Choose an option", choices=["1", "2", "3", "4", "5", "6"], default="6")

        if choice == "1":
            add_book()
        elif choice == "2":
            edit_book()
        elif choice == "3":
            delete_book()
        elif choice == "4":
            view_book()
        elif choice == "5":
            list_books()
        elif choice == "6":
            break

# Add a new book
def add_book():
    clear_screen()
    console.print("[bold green]=== Add Book ===[/bold green]")
    book_title = Prompt.ask("Enter book title").strip()
    if book_title in library:
        console.print(":warning: [red]Book already exists! Try a different title.[/red]")
    else:
        library[book_title] = {}
        console.print(f":white_check_mark: [green]Book '{book_title}' added successfully![/green]")

# Edit a book (manage chapters)
def edit_book():
    clear_screen()
    console.print("[bold green]=== Edit Book ===[/bold green]")
    list_books()
    book_title = Prompt.ask("Enter the title of the book to edit").strip()
    if book_title in library:
        manage_chapters_menu(book_title)
    else:
        console.print(":warning: [red]Book not found![/red]")

# Delete a book
def delete_book():
    clear_screen()
    console.print("[bold red]=== Delete Book ===[/bold red]")
    list_books()
    book_title = Prompt.ask("Enter the title of the book to delete").strip()
    if book_title in library:
        del library[book_title]
        console.print(f":wastebasket: [green]Book '{book_title}' deleted successfully![/green]")
    else:
        console.print(":warning: [red]Book not found![/red]")

# View a book (read chapters)
def view_book():
    clear_screen()
    console.print("[bold cyan]=== View Book ===[/bold cyan]")
    list_books()
    book_title = Prompt.ask("Enter the title of the book to view").strip()
    if book_title in library:
        read_book(book_title)
    else:
        console.print(":warning: [red]Book not found![/red]")

# List all books
def list_books():
    clear_screen()
    console.print("[bold cyan]=== List of Books ===[/bold cyan]")
    if not library:
        console.print(":open_book: [yellow]No books in the library.[/yellow]")
    else:
        table = Table(title="Books in Library")
        table.add_column("No.", style="dim", width=5)
        table.add_column("Title", justify="left")
        for i, title in enumerate(library.keys(), 1):
            table.add_row(str(i), title)
        console.print(table)

# Manage chapters of a book
def manage_chapters_menu(book_title):
    while True:
        clear_screen()
        console.print(f"[bold cyan]=== Manage Chapters of '{book_title}' ===[/bold cyan]")
        console.print("1. ➕ Add Chapter")
        console.print("2. ✏️ Edit Chapter")
        console.print("3. 🗑️ Delete Chapter")
        console.print("4. 📖 List Chapters")
        console.print("5. 🔙 Back to Library Menu")
        choice = Prompt.ask("Choose an option", choices=["1", "2", "3", "4", "5"], default="5")

        if choice == "1":
            add_chapter(book_title)
        elif choice == "2":
            edit_chapter(book_title)
        elif choice == "3":
            delete_chapter(book_title)
        elif choice == "4":
            list_chapters(book_title)
        elif choice == "5":
            break

# Add chapter to a book
def add_chapter(book_title):
    clear_screen()
    console.print("[bold green]=== Add Chapter ===[/bold green]")
    chapter_title = Prompt.ask("Enter chapter title").strip()
    if chapter_title in library[book_title]:
        console.print(":warning: [red]Chapter already exists! Try a different title.[/red]")
    else:
        content = Prompt.ask("Enter chapter content").strip()
        library[book_title][chapter_title] = content
        console.print(f":white_check_mark: [green]Chapter '{chapter_title}' added successfully!")

# Main program execution
if __name__ == "__main__":
    clear_screen()
    display_banner()
    load_data()
    main_menu()
    time.sleep(3)
    clear_screen()
    close_term()
