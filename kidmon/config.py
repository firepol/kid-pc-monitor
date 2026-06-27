"""Configuration for Kid PC Monitor.

All settings are read from a ``config.ini`` file at the repository root. The
file is optional: every value falls back to a built-in default defined here, so
a fresh checkout runs with no config file at all.

``config.ini`` is gitignored (it is per-machine). ``config.ini.example`` is the
committed template. The installers write a ``config.ini`` from it.

Unlike the old split deployment (separate agent + parent panel), there is now a
single app per kid PC, so there is a single web port and the parent points a
browser straight at ``http://<kid-ip>:<web port>``.

Sections
--------
[web]           — port, and the admin login (username + password hash).
[limits]        — per-weekday daily allowance in minutes, plus a default.
[notifications] — sound on/off, wav file, and the minute thresholds to alert at.
[monitoring]    — which OS users to monitor/exempt, and the grace-period length.
[activity]      — foreground-program logging on/off and poll interval.
[storage]       — SQLite database path.

Helper functions read ``CONFIG_PATH`` lazily on each call, so tests can point it
at a throwaway file. Malformed values fall back to the default rather than
crashing the running agent.
"""
import configparser
import os

from .notification_logic import parse_notify

# config.ini lives at the repo root (the parent of this kidmon/ directory).
# Using __file__ makes the path independent of the current working directory.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(_REPO_ROOT, "config.ini")

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday",
            "friday", "saturday", "sunday"]

# Built-in defaults — the single source of truth.
DEFAULTS = {
    "web": {
        "port": 9999,            # the one web UI port (kid status + admin)
        "username": "parent",    # admin login name
        "password_hash": "",     # werkzeug hash; empty => admin login disabled
    },
    "limits": {
        # Daily allowance in minutes. Per-weekday keys override "default".
        "default": 120,
        # monday..sunday: unset => fall back to default.
    },
    "notifications": {
        "sound_enabled": True,
        "sound_file": "",                 # default/fallback .wav; empty => beep
        "thresholds": "15,5,2,1",         # legacy: marks to alert at (one sound)
        "notify": "",                     # preferred: "15:gentle, 5:urgent, 1:urgent"
        "popup_enabled": False,           # also show an on-screen popup?
    },
    "monitoring": {
        "monitored_users": "",            # comma list; empty => all (minus exempt)
        "exempt_users": "",               # comma list of users never restricted
        "grace_period_seconds": 60,       # once-per-day post-lock save window
    },
    "activity": {
        "enabled": True,
        "interval_seconds": 15,           # how often to sample the foreground app
    },
    "storage": {
        "db_path": "kidmon.db",           # relative to the repo root
    },
}

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def _parser():
    parser = configparser.ConfigParser()
    parser.read(CONFIG_PATH)  # silently ignores a missing file
    return parser


def set_values(section, mapping):
    """Update config.ini in place, merging ``mapping`` into ``[section]``.

    Reads the current file (if any), applies the given keys, and writes it back,
    preserving every other section and key. Used by the installers and
    ``set_password.py``. Returns the path written.
    """
    parser = _parser()
    if not parser.has_section(section):
        parser.add_section(section)
    for key, value in mapping.items():
        parser[section][key] = str(value)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        parser.write(f)
    return CONFIG_PATH


def _get(section, key):
    """Raw string for [section] key from config.ini, or None if absent."""
    parser = _parser()
    if parser.has_section(section) and key in parser[section]:
        return parser[section][key].strip()
    return None


def _get_int(section, key, default):
    raw = _get(section, key)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _get_bool(section, key, default):
    raw = _get(section, key)
    if raw is None:
        return default
    low = raw.strip().lower()
    if low in _TRUE_VALUES:
        return True
    if low in _FALSE_VALUES:
        return False
    return default


def _get_str(section, key, default):
    raw = _get(section, key)
    return default if raw is None else raw


def _csv(value):
    """Split a comma-separated config value into a clean list of strings."""
    return [item.strip() for item in value.split(",") if item.strip()]


# --- web ---------------------------------------------------------------------

def get_web_port():
    return _get_int("web", "port", DEFAULTS["web"]["port"])


def get_admin_credentials():
    """Return (username, password_hash). password_hash is "" when unset."""
    username = _get_str("web", "username", DEFAULTS["web"]["username"])
    password_hash = _get_str("web", "password_hash", DEFAULTS["web"]["password_hash"])
    return username, password_hash


# --- limits ------------------------------------------------------------------

def get_default_limit():
    return _get_int("limits", "default", DEFAULTS["limits"]["default"])


def get_weekday_limits():
    """Return a dict of weekday-name -> minutes for any weekday explicitly set.

    Weekdays left unset are simply absent; callers fall back to the default via
    ``kidmon.schedule_logic.limit_for_weekday``.
    """
    limits = {}
    for name in WEEKDAYS:
        raw = _get("limits", name)
        if raw is not None and raw != "":
            try:
                limits[name] = int(raw)
            except ValueError:
                pass
    return limits


# --- notifications -----------------------------------------------------------

def get_sounds():
    """Return the ``[sounds]`` name -> path map (names are lower-cased)."""
    parser = _parser()
    if parser.has_section("sounds"):
        return {name.lower(): path.strip()
                for name, path in parser.items("sounds")}
    return {}


def _resolve_sound(path):
    """Absolute path for a sound file (relative paths are repo-root relative)."""
    if not path:
        return None
    return path if os.path.isabs(path) else os.path.join(_REPO_ROOT, path)


def get_notification_settings():
    """Resolve notification config into thresholds + a minute->sound map.

    Two ways to configure the marks:

    * ``notify = 15:gentle, 5:urgent`` (preferred) — minutes are the thresholds
      and each plays its named sound from ``[sounds]``; a missing/unknown name
      falls back to ``sound_file``.
    * ``thresholds = 15,5,1`` (legacy) — the single ``sound_file`` plays at every
      mark.

    Returns sound_enabled, popup_enabled, the descending ``thresholds`` list, a
    ``sound_by_minute`` map (minute -> resolved path or None), and the resolved
    ``default_sound`` (None means a system beep).
    """
    default_sound = _resolve_sound(
        _get_str("notifications", "sound_file",
                 DEFAULTS["notifications"]["sound_file"]).strip())
    sounds_map = get_sounds()

    notify_raw = _get_str("notifications", "notify",
                          DEFAULTS["notifications"]["notify"]).strip()
    if notify_raw:
        pairs = parse_notify(notify_raw)  # [(minute, name_or_None)], desc
        thresholds = [minute for minute, _ in pairs]
        sound_by_minute = {}
        for minute, name in pairs:
            resolved = _resolve_sound(sounds_map.get(name.lower())) if name else None
            sound_by_minute[minute] = resolved or default_sound
    else:
        thresholds = []
        for item in _csv(_get_str("notifications", "thresholds",
                                  DEFAULTS["notifications"]["thresholds"])):
            try:
                thresholds.append(int(item))
            except ValueError:
                pass
        thresholds.sort(reverse=True)
        sound_by_minute = {m: default_sound for m in thresholds}

    if not thresholds:
        thresholds = [15, 5, 1]
        sound_by_minute = {m: default_sound for m in thresholds}

    return {
        "sound_enabled": _get_bool("notifications", "sound_enabled",
                                   DEFAULTS["notifications"]["sound_enabled"]),
        "popup_enabled": _get_bool("notifications", "popup_enabled",
                                   DEFAULTS["notifications"]["popup_enabled"]),
        "thresholds": thresholds,
        "sound_by_minute": sound_by_minute,
        "default_sound": default_sound,
    }


# --- monitoring --------------------------------------------------------------

def get_monitoring_settings():
    return {
        "monitored_users": _csv(_get_str("monitoring", "monitored_users", "")),
        "exempt_users": _csv(_get_str("monitoring", "exempt_users", "")),
        "grace_period_seconds": _get_int(
            "monitoring", "grace_period_seconds",
            DEFAULTS["monitoring"]["grace_period_seconds"]),
    }


# --- activity ----------------------------------------------------------------

def get_activity_settings():
    return {
        "enabled": _get_bool("activity", "enabled",
                             DEFAULTS["activity"]["enabled"]),
        "interval_seconds": _get_int("activity", "interval_seconds",
                                     DEFAULTS["activity"]["interval_seconds"]),
    }


# --- storage -----------------------------------------------------------------

def get_db_path():
    """Absolute path to the SQLite database (resolved against the repo root)."""
    raw = _get_str("storage", "db_path", DEFAULTS["storage"]["db_path"])
    if os.path.isabs(raw):
        return raw
    return os.path.join(_REPO_ROOT, raw)
