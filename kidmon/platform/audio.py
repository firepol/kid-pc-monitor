"""Best-effort playback of warning sounds in many formats.

To stay dependency-free, the agent plays sounds through whatever command-line
player happens to be on PATH rather than bundling an audio library:

* ``ffplay`` (from ffmpeg) or ``mpv`` — the broadest support: wav, mp3, opus,
  ogg, flac, m4a/aac, wma, …  Install one of these if you want non-wav sounds.

Each platform backend additionally has a zero-dependency fallback for plain
**WAV** (``winsound`` on Windows, ``aplay``/``paplay`` on Linux), so ``.wav``
files always work out of the box with nothing extra installed.

``play_file`` returns True if it managed to run a player, False otherwise (so a
caller can fall back to its own WAV path). It never raises.
"""
import shutil
import subprocess

# General-purpose players that handle compressed formats (opus/mp3/ogg/…).
# Each entry is (executable, extra-args-to-play-once-and-exit-quietly).
_RICH_PLAYERS = [
    ("ffplay", ["-nodisp", "-autoexit", "-loglevel", "quiet"]),
    ("mpv", ["--no-video", "--really-quiet"]),
]


def find_player():
    """Return ``(exe_path, base_args)`` for the first rich player on PATH, or None."""
    for name, args in _RICH_PLAYERS:
        exe = shutil.which(name)
        if exe:
            return exe, args
    return None


def play_file(path, timeout=30):
    """Play an audio file via ffplay/mpv. True if a player ran, else False."""
    found = find_player()
    if not found:
        return False
    exe, args = found
    try:
        subprocess.run([exe, *args, path], capture_output=True, timeout=timeout)
        return True
    except Exception:
        return False
