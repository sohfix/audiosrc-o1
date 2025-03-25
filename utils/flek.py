import argparse
import os
from pathlib import Path

from PIL import Image


def truncate_filename(filename, max_length=10):
    """Truncate filename to a max of 10 characters, preserving the extension."""
    return filename[:max_length]


def convert_webp_to(image_path, output_dir, format, truncate=False):
    """Convert a WebP file to the specified format (PNG/JPEG) with optional truncation."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    img = Image.open(image_path)
    output_ext = "png" if format == "PNG" else "jpg"

    filename = image_path.stem
    if truncate:
        filename = truncate_filename(filename)

    output_file = output_dir / f"{filename}.{output_ext}"

    img = img.convert("RGBA") if format == "PNG" else img.convert("RGB")
    img.save(output_file, format=format, quality=95)

    print(f"Converted: {image_path} -> {output_file}")


def process_directory(input_dir, output_dir, format, truncate):
    """Convert all .webp files in a directory."""
    input_dir = Path(input_dir)
    if not input_dir.is_dir():
        print(f"Error: {input_dir} is not a valid directory.")
        return

    webp_files = list(input_dir.glob("*.webp"))
    if not webp_files:
        print("No .webp files found in", input_dir)
        return

    for file in webp_files:
        convert_webp_to(file, output_dir, format, truncate)


def main():
    parser = argparse.ArgumentParser(description="Convert WebP files to PNG or JPEG.")
    parser.add_argument("input", help="Input file or directory containing .webp files")
    parser.add_argument(
        "-o", "--output", default=None, help="Output directory (default: same as input)"
    )
    parser.add_argument("--png", action="store_true", help="Convert to PNG")
    parser.add_argument("--jpeg", action="store_true", help="Convert to JPEG")
    parser.add_argument(
        "-jc",
        "--junc",
        action="store_true",
        help="Truncate output filename to 10 characters",
    )

    args = parser.parse_args()

    if not args.png and not args.jpeg:
        print("Error: You must specify either --png or --jpeg.")
        return

    format = "PNG" if args.png else "JPEG"
    input_path = Path(args.input)

    if args.output:
        output_dir = Path(args.output)
    else:
        output_dir = input_path if input_path.is_dir() else input_path.parent

    if input_path.is_dir():
        process_directory(input_path, output_dir, format, args.junc)
    elif input_path.is_file() and input_path.suffix.lower() == ".webp":
        convert_webp_to(input_path, output_dir, format, args.junc)
    else:
        print(
            "Error: Input must be a .webp file or a directory containing .webp files."
        )


if __name__ == "__main__":
    main()
