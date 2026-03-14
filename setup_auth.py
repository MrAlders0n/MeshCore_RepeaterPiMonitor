#!/usr/bin/env python3
"""
setup_auth.py — Interactive password setup for RepeaterWatch.

Run as the meshcoremon service user:
    sudo -u meshcoremon /opt/RepeaterWatch/venv/bin/python3 /opt/RepeaterWatch/setup_auth.py

This script:
  1. Prompts for a new password (input is hidden)
  2. Bcrypt-hashes it
  3. Writes MESHCORE_PASSWORD_HASH to .env
  4. Clears any plaintext MESHCORE_PASSWORD from .env
"""

import getpass
import os
import sys

ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")


def upsert(lines, key, value):
    found = False
    out = []
    for line in lines:
        if line.startswith(key + "="):
            out.append(f"{key}={value}\n")
            found = True
        else:
            out.append(line)
    if not found:
        out.append(f"{key}={value}\n")
    return out


def main():
    try:
        import bcrypt
    except ImportError:
        print("ERROR: bcrypt not installed. Run: pip install bcrypt --break-system-packages")
        sys.exit(1)

    if not os.path.exists(ENV_PATH):
        print(f"ERROR: .env not found at {ENV_PATH}")
        sys.exit(1)

    print("RepeaterWatch — Password Setup")
    print("=" * 40)

    pw = getpass.getpass("New password: ")
    if not pw:
        print("ERROR: Password cannot be empty.")
        sys.exit(1)

    pw2 = getpass.getpass("Confirm password: ")
    if pw != pw2:
        print("ERROR: Passwords do not match.")
        sys.exit(1)

    pw_hash = bcrypt.hashpw(pw.encode(), bcrypt.gensalt(rounds=12)).decode()

    with open(ENV_PATH) as f:
        lines = f.readlines()

    # Set hashed password, clear plaintext
    lines = upsert(lines, "MESHCORE_PASSWORD_HASH", pw_hash)
    lines = upsert(lines, "MESHCORE_PASSWORD", "")

    with open(ENV_PATH, "w") as f:
        f.writelines(lines)

    print("Password updated successfully.")
    print("Restart RepeaterWatch for changes to take effect:")
    print("  sudo systemctl restart RepeaterWatch")


if __name__ == "__main__":
    main()
