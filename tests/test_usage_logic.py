"""Unit tests for usage-time accounting (src/usage_logic.py).

Pure and dependency-free: run with `python tests/test_usage_logic.py` (or via
pytest). No tkinter / Windows needed.

These pin down the fix for the bug where time spent with the PC locked still
counted toward the daily usage limit: locked time must be excluded, and the
limit effectively pauses while the screen is locked.
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from kidmon.usage_logic import usage_minutes, locked_delta  # noqa: E402

START = datetime(2026, 6, 27, 10, 0, 0)


def check(name, got, want):
    assert got == want, f"{name}: expected {want!r}, got {got!r}"
    print(f"  ok: {name}")


def approx(name, got, want, tol=1e-9):
    assert abs(got - want) <= tol, f"{name}: expected ~{want}, got {got}"
    print(f"  ok: {name}")


def at(minutes):
    """A time `minutes` after START."""
    return START + timedelta(minutes=minutes)


def test_no_lock_counts_full_wall_clock():
    # 30 minutes elapsed, never locked -> 30 minutes used.
    approx("never locked", usage_minutes(at(30), START, timedelta(0), None), 30.0)


def test_completed_lock_is_excluded():
    # 30 min elapsed, of which 10 were spent locked (and unlocked again).
    approx("banked locked excluded",
           usage_minutes(at(30), START, timedelta(minutes=10), None), 20.0)


def test_usage_frozen_while_locked():
    # Locked at the 20-min mark; now it's the 30-min mark (10 min locked,
    # in progress). Usage should stay at 20 — the limit is paused.
    locked_at = at(20)
    approx("frozen at lock-in",
           usage_minutes(at(30), START, timedelta(0), locked_at), 20.0)
    # Still 20 even later, as long as it stays locked.
    approx("still frozen later",
           usage_minutes(at(90), START, timedelta(0), locked_at), 20.0)


def test_resumes_after_unlock():
    # 20 min active, then locked 10 min (banked), then 5 more active minutes.
    # now = 35 min after start; used = 20 + 5 = 25.
    approx("resumes after unlock",
           usage_minutes(at(35), START, timedelta(minutes=10), None), 25.0)


def test_banked_plus_in_progress_lock():
    # 10 min banked from an earlier lock, plus an in-progress lock that began at
    # the 40-min mark; now is the 50-min mark. elapsed 50 - (10 + 10) = 30.
    approx("banked + in-progress",
           usage_minutes(at(50), START, timedelta(minutes=10), at(40)), 30.0)


def test_never_negative():
    # Pathological: more locked time than elapsed -> clamp to 0, not negative.
    approx("clamped to zero",
           usage_minutes(at(5), START, timedelta(minutes=10), None), 0.0)


def test_locked_delta_in_progress():
    # locked_delta counts banked time plus the open lock up to `now`.
    got = locked_delta(at(50), timedelta(minutes=10), at(40))
    check("locked_delta in progress", got, timedelta(minutes=20))


def test_locked_delta_no_open_lock():
    check("locked_delta banked only",
          locked_delta(at(50), timedelta(minutes=7), None), timedelta(minutes=7))


def main():
    tests = [
        test_no_lock_counts_full_wall_clock,
        test_completed_lock_is_excluded,
        test_usage_frozen_while_locked,
        test_resumes_after_unlock,
        test_banked_plus_in_progress_lock,
        test_never_negative,
        test_locked_delta_in_progress,
        test_locked_delta_no_open_lock,
    ]
    for t in tests:
        print(t.__name__)
        t()
    print("\nAll usage_logic tests passed.")


if __name__ == "__main__":
    main()
