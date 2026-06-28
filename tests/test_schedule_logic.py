"""Unit tests for per-weekday allowance selection (kidmon/schedule_logic.py).

Pure and dependency-free: run with `python tests/test_schedule_logic.py`.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, time as dtime  # noqa: E402

from kidmon.schedule_logic import (  # noqa: E402
    limit_for_weekday, scheduled_lock_active, WEEKDAYS,
)


def check(name, got, want):
    assert got == want, f"{name}: expected {want!r}, got {got!r}"
    print(f"  ok: {name}")


def test_falls_back_to_default_when_unset():
    # Monday=0 not configured -> default.
    check("unset weekday -> default", limit_for_weekday(0, {}, 120), 120)


def test_configured_day_wins():
    per_day = {"saturday": 240}
    sat = WEEKDAYS.index("saturday")
    check("configured saturday", limit_for_weekday(sat, per_day, 120), 240)
    mon = WEEKDAYS.index("monday")
    check("other day still default", limit_for_weekday(mon, per_day, 120), 120)


def test_explicit_none_means_unlimited_and_overrides_default():
    per_day = {"sunday": None}
    sun = WEEKDAYS.index("sunday")
    check("explicit None overrides default",
          limit_for_weekday(sun, per_day, 120), None)


def test_default_none_is_no_limit():
    check("default None -> None", limit_for_weekday(2, {}, None), None)


def test_all_weekdays_indexable():
    per_day = {name: i * 10 for i, name in enumerate(WEEKDAYS)}
    for i, name in enumerate(WEEKDAYS):
        check(f"{name} index", limit_for_weekday(i, per_day, 0), i * 10)


def test_scheduled_lock_holds_after_trigger_minute():
    locks = [dtime(21, 0)]
    check("at 21:00 locked",
          scheduled_lock_active(datetime(2026, 6, 27, 21, 0), locks, 600), True)
    # The bug was that one minute later it unlocked; now it holds.
    check("at 21:01 still locked",
          scheduled_lock_active(datetime(2026, 6, 27, 21, 1), locks, 600), True)
    check("at 23:30 still locked",
          scheduled_lock_active(datetime(2026, 6, 27, 23, 30), locks, 600), True)


def test_scheduled_lock_window_crosses_midnight():
    locks = [dtime(21, 0)]  # 21:00 + 600min = 07:00 next day
    check("00:30 (next day) still locked",
          scheduled_lock_active(datetime(2026, 6, 28, 0, 30), locks, 600), True)
    check("06:59 still locked",
          scheduled_lock_active(datetime(2026, 6, 28, 6, 59), locks, 600), True)
    check("07:01 unlocked",
          scheduled_lock_active(datetime(2026, 6, 28, 7, 1), locks, 600), False)


def test_scheduled_lock_inactive_before_trigger():
    locks = [dtime(21, 0)]
    check("20:59 not yet locked",
          scheduled_lock_active(datetime(2026, 6, 27, 20, 59), locks, 600), False)
    check("no lock times -> inactive",
          scheduled_lock_active(datetime(2026, 6, 27, 21, 0), [], 600), False)


def test_scheduled_lock_zero_duration_is_exact_minute():
    locks = [dtime(21, 0)]
    check("exact minute matches",
          scheduled_lock_active(datetime(2026, 6, 27, 21, 0), locks, 0), True)
    check("one minute later does not (legacy)",
          scheduled_lock_active(datetime(2026, 6, 27, 21, 1), locks, 0), False)


def main():
    for t in [
        test_falls_back_to_default_when_unset,
        test_configured_day_wins,
        test_explicit_none_means_unlimited_and_overrides_default,
        test_default_none_is_no_limit,
        test_all_weekdays_indexable,
        test_scheduled_lock_holds_after_trigger_minute,
        test_scheduled_lock_window_crosses_midnight,
        test_scheduled_lock_inactive_before_trigger,
        test_scheduled_lock_zero_duration_is_exact_minute,
    ]:
        print(t.__name__)
        t()
    print("\nAll schedule tests passed.")


if __name__ == "__main__":
    main()
