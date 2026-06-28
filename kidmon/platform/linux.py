"""Linux backend for the platform abstraction.

Targets a typical desktop Linux session. Because the Linux desktop landscape is
fragmented, each capability tries a couple of common tools and degrades
gracefully (returns a safe default, never raises) when none are available:

* lock / is_locked  — ``loginctl`` (systemd-logind) first, then
                      ``xdg-screensaver`` / ``gnome-screensaver-command``.
* foreground app    — ``xdotool`` to get the active window + its PID, then the
                      process name from ``/proc/<pid>/comm``. X11 only.
* sound             — ``ffplay``/``mpv`` (any format) then ``paplay``/``aplay``
                      (wav, plus ogg/flac via paplay); ``notify-send`` for popups.

Wayland sessions don't expose the active window to ``xdotool``, so activity
tracking may return None there; that's logged once and tolerated.
"""
import getpass
import logging
import os
import shutil
import subprocess
import threading

from . import audio
from .base import PlatformOps

logger = logging.getLogger("kidmon.platform.linux")


def _which(name):
    return shutil.which(name)


def _run(args, timeout=5):
    """Run a command, return stdout (str) or None on any failure."""
    try:
        out = subprocess.run(args, capture_output=True, text=True,
                             timeout=timeout)
        if out.returncode == 0:
            return out.stdout
        return None
    except Exception:
        return None


class LinuxOps(PlatformOps):
    def __init__(self):
        self._session_id = os.environ.get("XDG_SESSION_ID")

    def current_user(self):
        return getpass.getuser()

    def is_locked(self):
        # Preferred: ask logind about this session's LockedHint.
        if _which("loginctl") and self._session_id:
            out = _run(["loginctl", "show-session", self._session_id,
                        "-p", "LockedHint", "--value"])
            if out is not None:
                return out.strip().lower() == "yes"
        # Fallback: GNOME screensaver active state.
        if _which("gnome-screensaver-command"):
            out = _run(["gnome-screensaver-command", "-q"])
            if out is not None:
                return "is active" in out.lower()
        # Unknown — assume unlocked so we don't wrongly pause the usage clock.
        return False

    def lock(self):
        if _which("loginctl"):
            if self._session_id:
                if _run(["loginctl", "lock-session", self._session_id]) is not None:
                    return
            if _run(["loginctl", "lock-session"]) is not None:
                return
        for cmd in (["xdg-screensaver", "lock"],
                    ["gnome-screensaver-command", "-l"],
                    ["dm-tool", "lock"]):
            if _which(cmd[0]) and _run(cmd) is not None:
                return
        logger.error("lock failed: no supported screen-lock tool found")

    def foreground_app(self):
        if not _which("xdotool"):
            return None
        win = _run(["xdotool", "getactivewindow"])
        if not win:
            return None
        win = win.strip()
        title_out = _run(["xdotool", "getwindowname", win])
        title = title_out.strip() if title_out else ""
        pid_out = _run(["xdotool", "getwindowpid", win])
        process = None
        if pid_out and pid_out.strip().isdigit():
            process = self._process_name(int(pid_out.strip()))
        return (process, title)

    def _process_name(self, pid):
        try:
            with open(f"/proc/{pid}/comm", "r") as f:
                return f.read().strip() or None
        except Exception:
            try:
                import psutil
                return psutil.Process(pid).name()
            except Exception:
                return None

    def play_sound(self, path=None):
        """Play a warning sound. ffplay/mpv handle any format (opus, mp3, ogg,
        flac, wav); paplay adds ogg/flac/wav; aplay is wav-only. Empty path or a
        total failure falls back to a terminal bell."""
        def _play():
            if path:
                # Broadest support first, then PulseAudio, then ALSA (wav-only).
                if audio.play_file(path):
                    return
                for player in ("paplay", "aplay"):
                    if _which(player) and _run([player, path], timeout=30) is not None:
                        return
                logger.warning(
                    "Could not play %s — install ffmpeg (ffplay) or mpv to use "
                    "non-wav sounds.", path)
            # No file (or playback failed): a terminal bell as a last resort.
            try:
                print("\a", end="", flush=True)
            except Exception:
                pass

        threading.Thread(target=_play, daemon=True).start()

    def notify(self, title, message):
        def _show():
            if _which("notify-send"):
                _run(["notify-send", title, message])
            else:
                logger.info("notify (no notify-send): %s — %s", title, message)

        threading.Thread(target=_show, daemon=True).start()
