#!/usr/bin/env python3
import argparse
import hashlib
import logging
import sys
import textwrap

def print_manual():
    manual = textwrap.dedent("""
        oo7 - File Hash Verification Utility - INTEGRITY
        ========================================

        NAME
            oo7.py - Compute and verify MD5 and SHA1 hashes for a file.

        SYNOPSIS
            oo7.py FILENAME [options]
            oo7.py man

        DESCRIPTION
            This utility computes cryptographic hash functions for a given file.
            It supports MD5 (Message-Digest Algorithm 5) and SHA1 (Secure Hash Algorithm 1)
            to help verify file integrity. You can also supply expected hash values to check
            against the computed digests.

            Cryptographic hash functions are mathematical algorithms that transform data
            of arbitrary size into a fixed-size string of characters (the hash digest). They
            are widely used for verifying data integrity, password storage, and digital signatures.

            MD5:
                - Produces a 128-bit (16-byte) hash value.
                - Historically popular for verifying data integrity.
                - Now considered insecure for cryptographic purposes due to collision vulnerabilities.

            SHA1:
                - Produces a 160-bit (20-byte) hash value.
                - Also widely used for integrity checks.
                - Similarly, is no longer recommended for security-critical applications because
                  of weaknesses exposed over time.

            For secure applications, consider using more robust algorithms like SHA-256 or SHA-3.

        OPTIONS
            FILENAME
                The file whose hashes will be computed.

            --md5 HASH
                Expected MD5 hash value to verify against the computed MD5 digest.

            --sha HASH
                Expected SHA1 hash value to verify against the computed SHA1 digest.

            --verbose
                Enable verbose output to display detailed computation steps.

            -V, --version
                Display version information of this utility.

            --logging
                Enable logging of the verification process to a log file (oo7.log).

        MANUAL
            Cryptography and Hash Functions:
                Cryptographic hash functions take an input (or 'message') and return a fixed-size
                string of bytes. The output (digest) is unique to each unique input. These functions
                are one-way, meaning that the original data cannot be easily recovered from the hash.
                They are essential in verifying the integrity of data and ensuring that no changes
                have been made.

            Recommended Literature:
                - "Applied Cryptography" by Bruce Schneier.
                - "Cryptography and Network Security" by William Stallings.
                - "Introduction to Modern Cryptography" by Jonathan Katz and Yehuda Lindell.
                - Various NIST publications for up-to-date cryptographic standards.

        EXAMPLES
            Compute hashes for a file with verbose output:
                ./oo7.py myfile.txt --verbose

            Verify a file's MD5 and SHA1 against expected values:
                ./oo7.py myfile.txt --md5 d41d8cd98f00b204e9800998ecf8427e --sha da39a3ee5e6b4b0d3255bfef95601890afd80709

        AUTHOR
            @SOHFIX

        VERSION
            oo7 version 1.0
    """)
    print(manual)

def calculate_hashes(filename):
    md5_hash = hashlib.md5()
    sha_hash = hashlib.sha1()
    try:
        with open(filename, 'rb') as f:
            while chunk := f.read(4096):
                md5_hash.update(chunk)
                sha_hash.update(chunk)
    except FileNotFoundError:
        sys.exit(f"Error: File '{filename}' not found.")
    return md5_hash.hexdigest(), sha_hash.hexdigest()

def main():
    # Check if the first argument is "man" to print the manual.
    if len(sys.argv) > 1 and sys.argv[1].lower() == "man":
        print_manual()
        sys.exit(0)

    parser = argparse.ArgumentParser(
        description="Verify MD5 and SHA1 hashes for a file.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("filename", help="File to verify")
    parser.add_argument("--md5", help="Expected MD5 hash value")
    parser.add_argument("--sha", help="Expected SHA1 hash value")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    parser.add_argument("-V", "--version", action="version", version="oo7.py version 1.0")
    parser.add_argument("--logging", action="store_true", help="Enable logging to oo7.log")

    args = parser.parse_args()

    if args.logging:
        logging.basicConfig(filename='oo7.log',
                            level=logging.INFO,
                            format='%(asctime)s - %(levelname)s - %(message)s')
        logging.info("Logging enabled")

    if args.verbose:
        print(f"Calculating hashes for file: {args.filename}")

    md5_digest, sha_digest = calculate_hashes(args.filename)

    if args.verbose:
        print(f"Computed MD5:  {md5_digest}")
        print(f"Computed SHA1: {sha_digest}")

    # Verify MD5 if an expected value is provided.
    if args.md5:
        if md5_digest.lower() == args.md5.lower():
            print("MD5 match.")
            if args.logging:
                logging.info("MD5 verification passed.")
        else:
            print("MD5 mismatch!")
            if args.logging:
                logging.error("MD5 verification failed.")

    # Verify SHA1 if an expected value is provided.
    if args.sha:
        if sha_digest.lower() == args.sha.lower():
            print("SHA1 match.")
            if args.logging:
                logging.info("SHA1 verification passed.")
        else:
            print("SHA1 mismatch!")
            if args.logging:
                logging.error("SHA1 verification failed.")

if __name__ == "__main__":
    main()
