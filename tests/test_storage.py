"""Unit tests for the SQLite storage layer (kidmon/storage.py).

Uses a throwaway temp database per test, so nothing touches the real db.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from kidmon.storage import Storage  # noqa: E402


def check(name, got, want):
    assert got == want, f"{name}: expected {want!r}, got {got!r}"
    print(f"  ok: {name}")


def _store():
    tmp = tempfile.TemporaryDirectory()
    return Storage(os.path.join(tmp.name, "k.db")), tmp


def test_state_roundtrip_and_default():
    s, tmp = _store()
    check("missing key -> default", s.get_state("nope", 42), 42)
    s.set_state("limit", 120)
    check("int roundtrip", s.get_state("limit"), 120)
    s.set_state("lock_times", ["21:0", "22:30"])
    check("list roundtrip", s.get_state("lock_times"), ["21:0", "22:30"])
    s.set_state("limit", None)
    check("None roundtrip", s.get_state("limit"), None)
    s.close()
    tmp.cleanup()


def test_state_many_atomic():
    s, tmp = _store()
    s.set_state_many({"a": 1, "b": "two", "c": None})
    check("a", s.get_state("a"), 1)
    check("b", s.get_state("b"), "two")
    check("c", s.get_state("c"), None)
    s.close()
    tmp.cleanup()


def test_daily_usage_upsert_and_history():
    s, tmp = _store()
    s.record_daily_usage("2026-06-27", 3600, 120)
    s.record_daily_usage("2026-06-27", 5400, 120)  # upsert same day
    s.record_daily_usage("2026-06-26", 1800, 90)
    hist = s.get_history()
    check("two distinct days", len(hist), 2)
    check("newest first", hist[0]["day"], "2026-06-27")
    check("upserted value", hist[0]["used_seconds"], 5400)
    s.close()
    tmp.cleanup()


def test_activity_summary_groups_by_process():
    s, tmp = _store()
    s.log_activity("2026-06-27T10:00:00", "chrome.exe", "YouTube", 15)
    s.log_activity("2026-06-27T10:00:15", "chrome.exe", "Docs", 15)
    s.log_activity("2026-06-27T10:00:30", "game.exe", "Minecraft", 15)
    rows = s.get_activity_summary(day="2026-06-27")
    by_proc = {r["process"]: r["total"] for r in rows}
    check("chrome aggregated", by_proc["chrome.exe"], 30)
    check("game aggregated", by_proc["game.exe"], 15)
    check("ordered by total desc", rows[0]["process"], "chrome.exe")
    s.close()
    tmp.cleanup()


def test_messages_roundtrip_chronological():
    s, tmp = _store()
    s.add_message("2026-06-27T10:00:00", "parent", "dinner in 5")
    s.add_message("2026-06-27T10:01:00", "kid", "ok!")
    msgs = s.get_messages()
    check("two messages", len(msgs), 2)
    check("chronological order", [m["body"] for m in msgs], ["dinner in 5", "ok!"])
    s.close()
    tmp.cleanup()


def main():
    for t in [
        test_state_roundtrip_and_default,
        test_state_many_atomic,
        test_daily_usage_upsert_and_history,
        test_activity_summary_groups_by_process,
        test_messages_roundtrip_chronological,
    ]:
        print(t.__name__)
        t()
    print("\nAll storage tests passed.")


if __name__ == "__main__":
    main()
