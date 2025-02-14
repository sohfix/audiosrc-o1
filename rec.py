#!/home/sohfix/PycharmProjects/audiosrc/audiosrc-env/bin/python

import argparse
import json
import os
import datetime

from rich.console import Console
from rich.table import Table

console = Console()

CONFIG_FILE = os.path.expanduser("~/.rec-config.json")
SUB_PARSING = {"On" : False}

def load_config():
    """Load configuration from ~/.rec-config.json, or return an empty dict if nonexistent."""
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_config(config):
    """Save configuration to ~/.rec-config.json."""
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)

def get_storage_file(storage_dir):
    """Return the path to goals.json within the specified storage directory."""
    return os.path.join(storage_dir, "goals.json")

def load_goals(storage_file):
    """Load goals from JSON; return an empty list if file is missing or invalid."""
    if not os.path.exists(storage_file):
        return []
    try:
        with open(storage_file, "r") as f:
            return json.load(f)
    except:
        return []

def save_goals(goals, storage_file):
    """Save goals to JSON in storage_file."""
    with open(storage_file, "w") as f:
        json.dump(goals, f, indent=2)

def build_goals_table(goals, title="Goals"):
    """Return a Rich Table populated with the given goals."""
    table = Table(title=title)
    table.add_column("#", justify="right", style="cyan", no_wrap=True)
    table.add_column("Goal", style="magenta")
    table.add_column("Date", style="green")
    table.add_column("Notes", style="yellow")
    table.add_column("Status", style="bold")
    table.add_column("Completion Date", style="dim")

    for idx, goal in enumerate(goals, start=1):
        status_icon = "✅ Complete" if goal["completed"] else "⏳ Pending"
        table.add_row(
            str(idx),
            goal["goal"],
            goal.get("date", "N/A"),
            goal.get("notes", ""),
            status_icon,
            goal["completion_date"] or "N/A"
        )
    return table

def list_goals(goals):
    """List all stored goals in a nicely formatted Rich table."""
    if not goals:
        console.print("[bold red]No goals found.[/bold red]")
        return
    table = build_goals_table(goals, title="All Goals")
    console.print(table)

def list_completed_goals(goals):
    """List only completed goals in a nicely formatted Rich table."""
    completed = [g for g in goals if g["completed"]]
    if not completed:
        console.print("[bold red]No completed goals found.[/bold red]")
        return
    table = build_goals_table(completed, title="Completed Goals")
    console.print(table)

def add_goal(goals, goal_text, date_str=None, notes=None):
    """Add a new goal to the list."""
    new_goal = {
        "goal": goal_text,
        "date": date_str or "",
        "notes": notes or "",
        "completed": False,
        "completion_date": None
    }
    goals.append(new_goal)
    console.print(f"[bold green]Added goal:[/bold green] '{goal_text}'")

def complete_goal(goals, goal_text):
    """Mark a specified goal (by text or partial match) as completed."""
    now_str = datetime.datetime.now().strftime("%m/%d/%Y %H:%M:%S")
    found = False
    for goal in goals:
        if goal_text.lower() in goal["goal"].lower():
            goal["completed"] = True
            goal["completion_date"] = now_str
            found = True

    if found:
        console.print(
            f"[bold yellow]Marked goal containing '{goal_text}' as complete on {now_str}.[/bold yellow]"
        )
    else:
        console.print(f"[bold red]No goal found containing '{goal_text}'.[/bold red]")

def main():
    parser = argparse.ArgumentParser(
        description="Simple CLI tool for tracking daily/weekly goals with Rich formatting."
    )

    #TODO subparsing
    if SUB_PARSING['On']:
        # Add subparsers for different commands:
        subparsers = parser.add_subparsers(dest="command", required=True)

        # Add 'add' subparser:
        add_parser = subparsers.add_parser("None", help="Add a none.")
        add_parser.add_argument("none_text", help="The none text.")


    parser.add_argument("-g", "--goal", help="Goal text or partial match for completion.")
    parser.add_argument("-d", "--date", help="Date for the goal in MM/DD/YYYY format.")
    parser.add_argument("-n", "--notes", help="Optional notes for the goal.")
    parser.add_argument("-c", "--complete", action="store_true",
                        help="Mark the specified goal as complete.")
    parser.add_argument("--list", action="store_true", help="List all goals.")
    parser.add_argument("-lc", "--list-complete", action="store_true",
                        help="List only completed goals.")
    parser.add_argument("--set-dir", help="Set the storage directory for goals.json.")

    args = parser.parse_args()

    # Load existing config, or {}
    config = load_config()

    # If user provided --set-dir, update config:
    if args.set_dir:
        config["storage_dir"] = os.path.abspath(os.path.expanduser(args.set_dir))
        save_config(config)
        console.print(f"[bold green]Storage directory set to:[/bold green] {config['storage_dir']}")

    # Ensure storage_dir is set, otherwise stop:
    if "storage_dir" not in config or not config["storage_dir"]:
        console.print("[bold red]No storage directory set. Please use --set-dir /path/to/dir[/bold red]")
        return

    storage_dir = config["storage_dir"]
    storage_file = get_storage_file(storage_dir)

    # Load goals from storage file
    goals = load_goals(storage_file)

    if args.list:
        list_goals(goals)
    elif args.list_complete:
        list_completed_goals(goals)
    elif args.goal and args.complete:
        complete_goal(goals, args.goal)
        save_goals(goals, storage_file)
    elif args.goal:
        add_goal(goals, args.goal, args.date, args.notes)
        save_goals(goals, storage_file)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
