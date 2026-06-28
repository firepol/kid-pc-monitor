#!/usr/bin/env python3
"""Set (or change) the parent admin password for the web UI.

Stores a salted werkzeug password *hash* in config.ini under [web]; the plain
password is never written to disk. Run on the kid PC after installing.

    python scripts/set_password.py                  # prompt for the password
    python scripts/set_password.py --password ...    # non-interactive

There is a single shared password (no username): every parent logs in with it
and just picks their own display name for chat at login. The kid status page
stays open (no login); only the /admin controls require the password.
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
    parser.add_argument("--password", help="password (omit to be prompted securely)")
    args = parser.parse_args()

    password = args.password
    if not password:
        password = getpass.getpass("New parent password: ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("Passwords do not match.")
            sys.exit(1)
    if not password:
        print("Empty password — aborting.")
        sys.exit(1)

    path = config.set_values("web", {
        "password_hash": generate_password_hash(password),
    })
    print(f"Saved admin password to {path}")


if __name__ == "__main__":
    main()
