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
import importlib.util
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from kidmon import config

TASK_NAME = "KidPCMonitor"
FIREWALL_RULE = "Kid PC Monitor (web)"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENT = os.path.join(REPO_ROOT, "agent.py")
REQUIREMENTS = os.path.join(REPO_ROOT, "requirements.txt")

# Packages the agent needs at runtime (psutil is optional, so not checked).
REQUIRED_MODULES = ["flask", "werkzeug"]


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
    # Start at logon for the current user. The program/args must be wrapped in
    # *double* quotes (Windows ignores single quotes), escaped as \" so they
    # survive the outer /tr "..." — otherwise a path with spaces (e.g. under
    # "Program Files") fails and the agent never launches.
    cmd = (
        f'schtasks /create /tn "{TASK_NAME}" /sc onlogon /rl highest /f '
        f'/tr "\\"{py}\\" \\"{AGENT}\\""'
    )
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print("Failed to create task:\n" + (result.stderr or result.stdout))
        return False
    print(f"Scheduled task '{TASK_NAME}' created (runs at logon).")
    _allow_on_battery()
    return True


def _allow_on_battery():
    """Let the task start and keep running on battery.

    schtasks /create can't set battery options, so Task Scheduler applies its
    defaults (don't start on battery / stop when going on battery) — which would
    leave a laptop unmonitored whenever it's unplugged. Clear them via PowerShell.
    """
    ps = (
        "$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries "
        "-DontStopIfGoingOnBatteries; "
        f"Set-ScheduledTask -TaskName '{TASK_NAME}' -Settings $s | Out-Null"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
        capture_output=True, text=True)
    if result.returncode == 0:
        print("Task set to run on battery too.")
    else:
        print("Warning: could not clear battery limits "
              "(task may not run on battery):\n" + (result.stderr or result.stdout))


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


def check_dependencies():
    """Confirm the agent's deps are importable in THIS interpreter.

    The scheduled task runs the very interpreter that runs this installer (its
    pythonw.exe), so checking imports in-process tells us exactly whether the
    agent will start at logon. Fail loudly now instead of silently later.
    """
    missing = [m for m in REQUIRED_MODULES if importlib.util.find_spec(m) is None]
    if not missing:
        return True
    print("\nERROR: required packages are not installed for the interpreter the")
    print("agent would run with:")
    print(f"  {sys.executable}")
    print(f"  missing: {', '.join(missing)}")
    print("\nInstall the requirements into THIS interpreter, then re-run the")
    print("installer with the same one (e.g. your virtualenv's python):")
    print(f'  "{sys.executable}" -m pip install -r "{REQUIREMENTS}"')
    return False


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

    # Show the interpreter that will be baked into the task, and verify it has
    # the agent's dependencies before registering anything.
    print(f"Agent will run with: {pythonw_path()}")
    if not check_dependencies():
        sys.exit(1)

    if create_task():
        open_firewall(config.get_web_port())
        print("\nDone. The agent starts at next logon (or run `python agent.py` now).")
        print("Set the parent password with: python scripts\\set_password.py")


if __name__ == "__main__":
    main()
