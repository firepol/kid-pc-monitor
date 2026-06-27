"""Unit tests for notification sound logic (kidmon/notification_logic.py)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from kidmon.notification_logic import parse_notify, select_sound  # noqa: E402


def check(name, got, want):
    assert got == want, f"{name}: expected {want!r}, got {got!r}"
    print(f"  ok: {name}")


def test_parse_basic_sorted_desc():
    check("parse + sort desc",
          parse_notify("5:bell, 15:gentle, 1:urgent"),
          [(15, "gentle"), (5, "bell"), (1, "urgent")])


def test_parse_missing_and_empty_name():
    check("empty name -> None",
          parse_notify("10:loud, 2:"), [(10, "loud"), (2, None)])
    check("no colon -> None", parse_notify("3"), [(3, None)])


def test_parse_skips_malformed_and_dedupes():
    check("skip non-int minute", parse_notify("x:bell, 5:ok"), [(5, "ok")])
    check("later duplicate wins", parse_notify("5:a, 5:b"), [(5, "b")])
    check("blank entries ignored", parse_notify(" , 1:a , "), [(1, "a")])


def test_select_exact_threshold():
    thresholds = [15, 5, 1]
    sounds = {15: "/g.wav", 5: "/b.wav", 1: "/u.wav"}
    check("exact 5 -> its sound", select_sound(5, thresholds, sounds), "/b.wav")
    check("exact 1 -> its sound", select_sound(1, thresholds, sounds), "/u.wav")


def test_select_between_marks_uses_recent_mark():
    thresholds = [15, 5, 1]
    sounds = {15: "/g.wav", 5: "/b.wav", 1: "/u.wav"}
    # 12 left: most recently reached mark is 15.
    check("12 -> 15's sound", select_sound(12, thresholds, sounds), "/g.wav")
    # 3 left: most recent mark is 5.
    check("3 -> 5's sound", select_sound(3, thresholds, sounds), "/b.wav")


def test_select_above_all_marks_returns_default():
    thresholds = [15, 5, 1]
    check("above largest -> default",
          select_sound(20, thresholds, {15: "/g.wav"}, default="/d.wav"), "/d.wav")


def test_select_zero_picks_most_urgent():
    thresholds = [15, 5, 1]
    sounds = {15: "/g.wav", 5: "/b.wav", 1: "/u.wav"}
    check("0 -> smallest mark's sound", select_sound(0, thresholds, sounds), "/u.wav")


def test_select_falls_back_when_mark_has_no_sound():
    thresholds = [15, 5, 1]
    sounds = {15: "/g.wav", 5: None, 1: "/u.wav"}
    check("None mark -> default",
          select_sound(5, thresholds, sounds, default="/d.wav"), "/d.wav")


def main():
    for t in [
        test_parse_basic_sorted_desc,
        test_parse_missing_and_empty_name,
        test_parse_skips_malformed_and_dedupes,
        test_select_exact_threshold,
        test_select_between_marks_uses_recent_mark,
        test_select_above_all_marks_returns_default,
        test_select_zero_picks_most_urgent,
        test_select_falls_back_when_mark_has_no_sound,
    ]:
        print(t.__name__)
        t()
    print("\nAll notification tests passed.")


if __name__ == "__main__":
    main()
