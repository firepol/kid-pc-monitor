#!/usr/bin/env python3
"""Install the Kid PC Monitor agent on a Windows kid PC.

Sets up the agent to start automatically at logon and opens the web port in
Windows Firewall so the parent can reach the UI from another device. Must be run
from an Administrator command prompt.

    python scripts\\install_windows.py            # install (uses config web port)
    python scripts\\install_windows.py --remove   # remove task + firewall rule

After installing, set the parent password with:
    python scripts\\set_password.py
"""
import argparse
import ctypes
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from kidmon import config

TASK_NAME = "KidPCMonitor"
FIREWALL_RULE = "Kid PC Monitor (web)"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENT = os.path.join(REPO_ROOT, "agent.py")


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def pythonw_path():
    """Prefer pythonw.exe so the agent runs without a console window."""
    base = os.path.dirname(sys.executable)
    candidate = os.path.join(base, "pythonw.exe")
    return candidate if os.path.exists(candidate) else sys.executable


def create_task():
    py = pythonw_path()
    # Start at logon for the current user; run whether on battery or not.
    cmd = (
        f'schtasks /create /tn "{TASK_NAME}" /sc onlogon /rl highest /f '
        f'/tr "\'{py}\' \'{AGENT}\'"'
    )
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"Scheduled task '{TASK_NAME}' created (runs at logon).")
        return True
    print("Failed to create task:\n" + (result.stderr or result.stdout))
    return False


def open_firewall(port):
    cmd = (
        f'netsh advfirewall firewall add rule name="{FIREWALL_RULE}" '
        f'dir=in action=allow protocol=TCP localport={port}'
    )
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"Opened TCP port {port} in Windows Firewall.")
    else:
        print("Could not add firewall rule:\n" + (result.stderr or result.stdout))


def remove():
    subprocess.run(f'schtasks /delete /tn "{TASK_NAME}" /f', shell=True)
    subprocess.run(f'netsh advfirewall firewall delete rule name="{FIREWALL_RULE}"',
                   shell=True)
    print("Removed scheduled task and firewall rule (if present).")


def main():
    parser = argparse.ArgumentParser(description="Install the agent on Windows.")
    parser.add_argument("--remove", action="store_true", help="uninstall instead")
    args = parser.parse_args()

    if not is_admin():
        print("This script must be run as Administrator.")
        sys.exit(1)

    if args.remove:
        remove()
        return

    if create_task():
        open_firewall(config.get_web_port())
        print("\nDone. The agent starts at next logon (or run `python agent.py` now).")
        print("Set the parent password with: python scripts\\set_password.py")


if __name__ == "__main__":
    main()
