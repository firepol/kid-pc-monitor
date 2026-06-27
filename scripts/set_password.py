#!/usr/bin/env python3
"""Set (or change) the parent admin password for the web UI.

Stores a salted werkzeug password *hash* in config.ini under [web]; the plain
password is never written to disk. Run on the kid PC after installing.

    python scripts/set_password.py                 # prompt for username+password
    python scripts/set_password.py --username mum  # set username too

The kid status page stays open (no login); only the /admin controls require it.
"""
import argparse
import getpass
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from werkzeug.security import generate_password_hash

from kidmon import config


def main():
    parser = argparse.ArgumentParser(description="Set the parent admin password.")
    parser.add_argument("--username", help="admin username (default: keep current)")
    parser.add_argument("--password", help="password (omit to be prompted securely)")
    args = parser.parse_args()

    current_user, _ = config.get_admin_credentials()
    username = args.username or current_user

    password = args.password
    if not password:
        password = getpass.getpass(f"New password for '{username}': ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("Passwords do not match.")
            sys.exit(1)
    if not password:
        print("Empty password — aborting.")
        sys.exit(1)

    path = config.set_values("web", {
        "username": username,
        "password_hash": generate_password_hash(password),
    })
    print(f"Saved admin login for '{username}' to {path}")


if __name__ == "__main__":
    main()
