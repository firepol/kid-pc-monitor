"""Unit tests for the once-per-day post-lock save-session decision logic.

Pure and dependency-free: run with `python tests/test_grace_logic.py` (or via
pytest). No tkinter / Windows needed.
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from grace_logic import (  # noqa: E402
    decide_grace_action,
    RESET, NONE, LOCK_NOW, GRANT_SESSION, RELOCK,
)

NOW = datetime(2026, 6, 26, 20, 0, 0)
TODAY = NOW.date()
YESTERDAY = (NOW - timedelta(days=1)).date()


def decide(should_lock=True, is_locked=False, over_limit_locked=False,
           grace_deadline=None, grace_used_date=None, grace_period_seconds=60,
           now=NOW):
    return decide_grace_action(now, should_lock, is_locked, over_limit_locked,
                               grace_deadline, grace_used_date, grace_period_seconds)


def check(name, got, want):
    assert got == want, f"{name}: expected {want!r}, got {got!r}"
    print(f"  ok: {name}")


def test_decide_grace_action():
    # Under the limit: episode resets regardless of other state.
    check("under limit -> reset", decide(should_lock=False), RESET)
    check("under limit while locked -> reset",
          decide(should_lock=False, is_locked=True, over_limit_locked=True), RESET)

    # First time over the limit while unlocked: immediate lock.
    check("first over-limit -> lock_now", decide(), LOCK_NOW)

    # At the lock screen: do nothing (no active save window).
    check("locked, no window -> none", decide(is_locked=True, over_limit_locked=True), NONE)

    # Re-login after the initial lock, grace unused today: grant the session.
    check("re-login, grace available -> grant",
          decide(over_limit_locked=True), GRANT_SESSION)

    # Re-login but grace already used today: re-lock immediately.
    check("re-login, grace used today -> relock",
          decide(over_limit_locked=True, grace_used_date=TODAY), RELOCK)

    # Grace used yesterday counts as available again (new day).
    check("re-login, grace used yesterday -> grant",
          decide(over_limit_locked=True, grace_used_date=YESTERDAY), GRANT_SESSION)

    # Save session running, deadline not reached: let them keep saving.
    check("session active, before deadline -> none",
          decide(over_limit_locked=True, grace_used_date=TODAY,
                 grace_deadline=NOW + timedelta(seconds=30)), NONE)

    # Save session running, deadline reached: re-lock.
    check("session active, deadline passed -> relock",
          decide(over_limit_locked=True, grace_used_date=TODAY,
                 grace_deadline=NOW - timedelta(seconds=1)), RELOCK)

    # Feature disabled (0s): re-login locks immediately, no session.
    check("grace disabled -> relock",
          decide(over_limit_locked=True, grace_period_seconds=0), RELOCK)

    # Safety net: window somehow outlived a lock and expired -> relock.
    check("locked with expired window -> relock",
          decide(is_locked=True, over_limit_locked=True,
                 grace_deadline=NOW - timedelta(seconds=1)), RELOCK)

    print("\nAll grace_logic tests passed.")


if __name__ == "__main__":
    test_decide_grace_action()
