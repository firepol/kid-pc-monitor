"""Pure usage-time accounting.

Active usage = elapsed wall-clock since the period started, MINUS the time the
screen was locked. Locked time must not count toward the daily usage limit, so
the kid isn't penalised for stepping away and locking the PC.

Kept pure and dependency-free (just datetime) so it can be unit-tested without
Windows/tkinter — see tests/test_usage_logic.py.
"""
from datetime import timedelta


def locked_delta(now, locked_accumulated, lock_started_at):
    """Total time spent locked so far this period.

    ``locked_accumulated`` is the banked locked time from completed locks;
    ``lock_started_at`` is the start of an in-progress lock (or None). The
    in-progress lock is counted up to ``now``.
    """
    if lock_started_at is not None:
        return locked_accumulated + (now - lock_started_at)
    return locked_accumulated


def usage_minutes(now, start_time, locked_accumulated, lock_started_at):
    """Active usage in minutes: (now - start_time) minus locked time.

    Never negative. While the screen is locked the result stays flat, because
    the in-progress locked time grows at the same rate as the elapsed time — so
    the usage limit is effectively paused until the PC is unlocked.
    """
    elapsed = (now - start_time) - locked_delta(now, locked_accumulated, lock_started_at)
    minutes = elapsed.total_seconds() / 60
    return minutes if minutes > 0 else 0.0
