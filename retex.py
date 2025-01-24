#!/home/sohfix/PycharmProjects/rehab/renv/bin/python3
import argparse
import subprocess
import os
import sys
from tqdm import tqdm
from termcolor import colored

# Version variable
VERSION = "1.0.0"

def compile_tex_to_pdf(tex_file, output_dir=None, keep=False, verbose=False):
    if not os.path.isfile(tex_file):
        print(colored(f"Error: The file '{tex_file}' does not exist.", "red"))
        sys.exit(1)

    # Create output directory if not existing
    if output_dir and not os.path.isdir(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    # Determine where auxiliary files will be located
    if output_dir:
        base_dir = output_dir
    else:
        base_dir = os.path.dirname(tex_file) or '.'

    # Base filename (without extension)
    base_name = os.path.splitext(os.path.basename(tex_file))[0]

    # Construct the pdflatex command
    command = ['pdflatex', '-interaction=nonstopmode']
    if output_dir:
        command.extend(['-output-directory', output_dir])
    command.append(tex_file)

    if verbose:
        print(colored("Running command:", "blue"), " ".join(command))

    try:
        with tqdm(total=100, desc="Compiling", bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt}") as pbar:
            process = subprocess.run(
                command,
                check=True,
                stdout=subprocess.PIPE if not verbose else None,
                stderr=subprocess.PIPE if not verbose else None
            )
            pbar.update(100)

        print(colored(f"Successfully compiled '{tex_file}' to PDF.", "green"))

        if not keep:
            aux_file = os.path.join(base_dir, f"{base_name}.aux")
            log_file = os.path.join(base_dir, f"{base_name}.log")
            removed_files = []
            for f in [aux_file, log_file]:
                if os.path.isfile(f):
                    os.remove(f)
                    removed_files.append(f)
                    if verbose:
                        print(colored(f"Removed '{f}'", "yellow"))

            if removed_files and not verbose:
                print(colored(f"Removed auxiliary files: {', '.join(removed_files)}", "yellow"))

    except subprocess.CalledProcessError as e:
        print(colored(f"Error during compilation: {e}", "red"))
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description=colored('Convert a .tex file to PDF with progress tracking.', "cyan"))
    parser.add_argument('tex_file', nargs='?', help=colored('Path to the .tex file', "blue"))
    parser.add_argument('-o', '--output-dir', help=colored('Directory to save the output PDF', "blue"), default=None)
    parser.add_argument('--keep', action='store_true', help=colored('Keep .aux and .log files after compilation', "blue"))
    parser.add_argument('-v', '--verbose', action='store_true', help=colored('Show compilation progress and details', "blue"))
    parser.add_argument('--version', action='version', version=colored(f"Version: {VERSION}", "green"))

    args = parser.parse_args()

    if args.tex_file:
        compile_tex_to_pdf(
            tex_file=args.tex_file,
            output_dir=args.output_dir,
            keep=args.keep,
            verbose=args.verbose
        )
    else:
        print(colored("Error: No .tex file provided. Use --help for usage instructions.", "red"))

if __name__ == '__main__':
    main()
