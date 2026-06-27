"""Pure decision logic for per-weekday daily allowances.

Given the per-weekday overrides from config and a default, decide today's
allowance in minutes. Kept dependency-free (no config / I/O) so it can be
unit-tested in isolation — see tests/test_schedule_logic.py.
"""

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday",
            "friday", "saturday", "sunday"]


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
