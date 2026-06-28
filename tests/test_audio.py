"""Tests for audio.play_file's success semantics.

play_file must report success only when the player actually played the file
(exit code 0). A missing/unreadable file makes ffplay/mpv exit non-zero, and
that must surface as False so the platform backends fall back to a beep instead
of silently playing nothing.

Run directly or under pytest.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kidmon.platform import audio  # noqa: E402


def check(label, got, expected):
    status = "ok" if got == expected else "FAIL"
    print(f"  [{status}] {label}: {got!r}")
    assert got == expected, f"{label}: expected {expected!r}, got {got!r}"


class _FakeCompleted:
    def __init__(self, returncode):
        self.returncode = returncode


def _with_player(monkey_returncode):
    """Patch find_player + subprocess.run; return (restore) callable."""
    orig_find = audio.find_player
    orig_run = audio.subprocess.run
    audio.find_player = lambda: ("/usr/bin/ffplay", [])
    audio.subprocess.run = lambda *a, **k: _FakeCompleted(monkey_returncode)

    def restore():
        audio.find_player = orig_find
        audio.subprocess.run = orig_run
    return restore


def test_no_player_returns_false():
    orig = audio.find_player
    audio.find_player = lambda: None
    try:
        check("no player -> False", audio.play_file("/snd/x.wav"), False)
    finally:
        audio.find_player = orig


def test_exit_zero_is_success():
    restore = _with_player(0)
    try:
        check("exit 0 -> True", audio.play_file("/snd/ok.wav"), True)
    finally:
        restore()


def test_nonzero_exit_is_failure():
    # A missing file makes ffplay/mpv exit non-zero; play_file must say False.
    restore = _with_player(1)
    try:
        check("exit 1 -> False", audio.play_file("/snd/missing.wav"), False)
    finally:
        restore()


def main():
    for t in (test_no_player_returns_false, test_exit_zero_is_success,
              test_nonzero_exit_is_failure):
        print(t.__name__)
        t()
    print("\nAll audio tests passed.")


if __name__ == "__main__":
    main()
