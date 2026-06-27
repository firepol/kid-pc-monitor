"""Shared configuration for Kid PC Monitor.

Ports (and any future settings) are read from a ``config.ini`` file at the
repository root. The file is optional: every value falls back to a built-in
default defined here, so a fresh checkout works with no config file at all.

``config.ini`` is gitignored (it is per-machine). ``config.ini.example`` is
committed as a template. The installer (``scripts/install.py``) also writes
``config.ini`` when the user picks a non-default port.

Note on the split deployment: the agent runs on each kid PC and the web panel
runs on the parent PC. They are different machines, each with their own
``config.ini``. The ``agent`` port must match on both for the panel to reach
the kid PC.
"""
import configparser
import os

# Built-in defaults — the single source of truth for the standard ports.
DEFAULTS = {
    "agent": 9999,            # pc_control.py RemoteControlServer (kid PC)
    "web_panel": 5000,        # web_panel.py Flask app (parent PC)
    "kid_status_page": 8080,  # read-only status page (kid PC); None to disable
}

# config.ini lives at the repo root (the parent of this src/ directory). Using
# __file__ makes the path independent of the current working directory, which
# matters because the scheduled task launches the agent from src/.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(_REPO_ROOT, "config.ini")

# Values that mean "disabled" for an optional port (the kid status page).
_DISABLED_VALUES = {"", "none", "off", "disabled", "0"}


def _read_section():
    """Return the [ports] section as a dict of raw strings (empty if absent)."""
    parser = configparser.ConfigParser()
    # parser.read silently ignores a missing file, which is exactly what we want.
    parser.read(CONFIG_PATH)
    if parser.has_section("ports"):
        return dict(parser.items("ports"))
    return {}


def get_ports():
    """Resolve all ports, applying config.ini over the built-in defaults.

    The ``kid_status_page`` value may be disabled (returns None); ``agent`` and
    ``web_panel`` always resolve to an int. Malformed values fall back to the
    default rather than crashing the agent or panel.
    """
    raw = _read_section()
    ports = {}
    for key, default in DEFAULTS.items():
        if key not in raw:
            ports[key] = default
            continue
        value = raw[key].strip()
        if key == "kid_status_page" and value.lower() in _DISABLED_VALUES:
            ports[key] = None
            continue
        try:
            ports[key] = int(value)
        except ValueError:
            ports[key] = default
    return ports


def write_ports(**overrides):
    """Write config.ini, merging the given port overrides over current values.

    Unspecified ports keep their current resolved value, so calling this with
    only ``agent=...`` preserves the others. Returns the path written.
    """
    ports = get_ports()
    for key, value in overrides.items():
        if key not in DEFAULTS:
            raise KeyError(f"Unknown port key: {key}")
        ports[key] = value

    parser = configparser.ConfigParser()
    parser["ports"] = {
        key: ("none" if value is None else str(value))
        for key, value in ports.items()
    }
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        parser.write(f)
    return CONFIG_PATH


_ports = get_ports()
AGENT_PORT = _ports["agent"]
WEB_PANEL_PORT = _ports["web_panel"]
KID_PAGE_PORT = _ports["kid_status_page"]
