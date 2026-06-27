"""Unit tests for per-weekday allowance selection (kidmon/schedule_logic.py).

Pure and dependency-free: run with `python tests/test_schedule_logic.py`.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from kidmon.schedule_logic import limit_for_weekday, WEEKDAYS  # noqa: E402


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


def main():
    for t in [
        test_falls_back_to_default_when_unset,
        test_configured_day_wins,
        test_explicit_none_means_unlimited_and_overrides_default,
        test_default_none_is_no_limit,
        test_all_weekdays_indexable,
    ]:
        print(t.__name__)
        t()
    print("\nAll schedule tests passed.")


if __name__ == "__main__":
    main()
