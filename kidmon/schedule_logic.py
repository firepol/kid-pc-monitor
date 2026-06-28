"""Pure decision logic for per-weekday daily allowances.

Given the per-weekday overrides from config and a default, decide today's
allowance in minutes. Kept dependency-free (no config / I/O) so it can be
unit-tested in isolation — see tests/test_schedule_logic.py.
"""
from datetime import timedelta

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday",
            "friday", "saturday", "sunday"]


def scheduled_lock_active(now, lock_times, duration_minutes):
    """True if ``now`` falls inside the lock window of any scheduled lock time.

    Each lock time T keeps the screen locked for ``duration_minutes`` after it,
    so a bedtime lock holds overnight (and survives sleep/clock skew) instead of
    matching only the single triggering minute. Windows that start the previous
    day and run past midnight are handled.

    ``duration_minutes <= 0`` falls back to the legacy exact-minute behaviour.
    """
    if duration_minutes <= 0:
        return any(now.hour == lt.hour and now.minute == lt.minute
                   for lt in lock_times)
    window = timedelta(minutes=duration_minutes)
    for lt in lock_times:
        start = now.replace(hour=lt.hour, minute=lt.minute,
                            second=0, microsecond=0)
        # Today's occurrence and yesterday's (its window may reach into today).
        for s in (start, start - timedelta(days=1)):
            if s <= now < s + window:
                return True
    return False


def limit_for_weekday(weekday_index, per_day, default):
    """Return the allowance (minutes) for a weekday, or None for "no limit".

    Args:
        weekday_index: Monday=0 .. Sunday=6 (datetime.date.weekday()).
        per_day: dict of weekday-name -> minutes for explicitly configured days
            (may be partial or empty). A value of None for a day means that day
            is explicitly unlimited and overrides the default.
        default: fallback minutes used for any day not present in per_day. May
            be None to mean "no limit by default".

    A configured day always wins over the default, including an explicit None
    (unlimited). Days absent from per_day fall back to default.
    """
    name = WEEKDAYS[weekday_index]
    if name in per_day:
        return per_day[name]
    return default
