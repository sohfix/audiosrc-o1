#!/home/sohfix/PycharmProjects/rehab/renv/bin/python3
import argparse
import subprocess
import os
import sys

def compile_tex_to_pdf(tex_file, output_dir=None, keep=False, verbose=False):
    if not os.path.isfile(tex_file):
        print(f"Error: The file '{tex_file}' does not exist.")
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
        print("Running command:", " ".join(command))

    try:
        if verbose:
            subprocess.run(command, check=True)
        else:
            subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        print(f"Successfully compiled '{tex_file}' to PDF.")

        if not keep:
            aux_file = os.path.join(base_dir, f"{base_name}.aux")
            log_file = os.path.join(base_dir, f"{base_name}.log")
            for f in [aux_file, log_file]:
                if os.path.isfile(f):
                    os.remove(f)
                    if verbose:
                        print(f"Removed '{f}'")

    except subprocess.CalledProcessError as e:
        print(f"Error during compilation: {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description='Convert a .tex file to PDF.')
    parser.add_argument('tex_file', help='Path to the .tex file')
    parser.add_argument('-o', '--output-dir', help='Directory to save the output PDF', default=None)
    parser.add_argument('--keep', action='store_true', help='Keep .aux and .log files after compilation')
    parser.add_argument('-v', '--verbose', action='store_true', help='Show compilation progress and details')
    args = parser.parse_args()

    compile_tex_to_pdf(
        tex_file=args.tex_file,
        output_dir=args.output_dir,
        keep=args.keep,
        verbose=args.verbose
    )

if __name__ == '__main__':
    main()
