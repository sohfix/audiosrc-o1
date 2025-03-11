#!/home/sohfix/PycharmProjects/audiosrc/audiosrc-env/bin/python

import argparse
import os
import sys
import shutil
import stat

VERSION = "1.0.1"

def make_executable(path):
    """
    Give the file at `path` user/group/world read and execute permissions (chmod 775).
    """
    current_mode = os.stat(path).st_mode
    # Grant read, write, execute (owner), and read, execute (group, others).
    new_mode = current_mode | stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH
    os.chmod(path, new_mode)

def copy_and_chmod(src_file, dist_dir, remove_py_ext=True, verbose=False):
    """
    Copy `src_file` to `dist_dir`. Optionally remove the .py extension and chmod to 775.
    Overwrite if the destination exists.
    """
    basename = os.path.basename(src_file)
    # Remove .py extension if requested
    if remove_py_ext and basename.lower().endswith(".py"):
        basename = os.path.splitext(basename)[0]

    dest_path = os.path.join(dist_dir, basename)

    # Perform the copy (overwrite if existing)
    shutil.copy2(src_file, dest_path)

    # Make the file executable for the user, group, others
    make_executable(dest_path)

    if verbose:
        print(f"Copied '{src_file}' -> '{dest_path}' [chmod 775]")

def main():
    # Hard-coded distribution folder
    dist_dir = os.path.expandvars("$HOME/programs/distribution")
    os.makedirs(dist_dir, exist_ok=True)

    parser = argparse.ArgumentParser(
        description="Copy Python files from a source directory into $HOME/programs/distribution, "
                    "removing the .py extension and chmod 775."
    )
    parser.add_argument("action",
                        choices=["copy"],
                        help="Action to perform (currently only 'copy' is supported).")
    # The source directory, default is the current directory
    parser.add_argument("-d", "--dir", default=".",
                        help="Source directory with .py files. Default is the current directory.")
    parser.add_argument("--all", action="store_true",
                        help="Automatically copy all .py files without asking.")
    parser.add_argument("-V", "--version", action="store_true",
                        help="Show the script version and exit.")
    parser.add_argument("--verbose", action="store_true",
                        help="Show verbose output (print each file copied).")

    args = parser.parse_args()

    # Show version if requested
    if args.version:
        print(f"upd version {VERSION}")
        sys.exit(0)

    if args.action == "copy":
        # Source directory is from arguments
        source_dir = os.path.abspath(args.dir)

        if not os.path.isdir(source_dir):
            print(f"Error: '{source_dir}' is not a valid directory.")
            sys.exit(1)

        # Gather all .py files in the source directory
        files_in_source = os.listdir(source_dir)
        py_files = [os.path.join(source_dir, f) for f in files_in_source
                    if f.endswith(".py") and os.path.isfile(os.path.join(source_dir, f))]

        if not py_files:
            print("No .py files found in the source directory.")
            sys.exit(0)

        if args.all:
            # Copy all .py files directly
            for py_file in py_files:
                copy_and_chmod(py_file, dist_dir, remove_py_ext=True, verbose=args.verbose)
        else:
            # Ask user which files to copy
            print("Select which .py files you want to copy (comma-separated list of indices):\n")
            for i, filepath in enumerate(py_files):
                print(f"  [{i}] {os.path.basename(filepath)}")

            selected = input("\nEnter file indices (e.g. 0,2,4) or 'a' for all: ").strip()

            if selected.lower() == 'a':
                # Copy all
                for py_file in py_files:
                    copy_and_chmod(py_file, dist_dir, remove_py_ext=True, verbose=args.verbose)
            else:
                try:
                    indices = [int(x) for x in selected.split(",")]
                except ValueError:
                    print("Invalid selection. Exiting.")
                    sys.exit(1)

                for idx in indices:
                    if idx < 0 or idx >= len(py_files):
                        print(f"Index {idx} is out of range. Skipping.")
                        continue
                    copy_and_chmod(py_files[idx], dist_dir, remove_py_ext=True, verbose=args.verbose)

        print("\nAll selected files have been processed.\n")

if __name__ == "__main__":
    main()
