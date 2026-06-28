"""Unit tests for the configuration loader (kidmon/config.py).

Pure and dependency-free: run with `python tests/test_config.py` (or via
pytest). Each test points config.CONFIG_PATH at a throwaway temp file, so the
real repo config.ini is never read or written.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from kidmon import config  # noqa: E402


def check(name, got, want):
    assert got == want, f"{name}: expected {want!r}, got {got!r}"
    print(f"  ok: {name}")


def _with_ini(contents):
    """Point config at a fresh temp config.ini; None means 'no file'."""
    tmp = tempfile.TemporaryDirectory()
    path = os.path.join(tmp.name, "config.ini")
    if contents is not None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(contents)
    config.CONFIG_PATH = path
    return tmp


def test_defaults_when_no_file():
    with _with_ini(None):
        check("default web port", config.get_web_port(), 9999)
        check("default daily limit", config.get_default_limit(), 120)
        check("no weekday overrides", config.get_weekday_limits(), {})
        user, pw = config.get_admin_credentials()
        check("default admin user", user, "parent")
        check("no password by default", pw, "")


def test_web_overrides():
    with _with_ini("[web]\nport = 8000\nusername = mum\npassword_hash = abc123\n"):
        check("web port overridden", config.get_web_port(), 8000)
        user, pw = config.get_admin_credentials()
        check("username overridden", user, "mum")
        check("password hash read", pw, "abc123")


def test_per_weekday_limits():
    ini = "[limits]\ndefault = 90\nsaturday = 240\nsunday = 180\n"
    with _with_ini(ini):
        check("default kept", config.get_default_limit(), 90)
        check("weekday overrides parsed",
              config.get_weekday_limits(), {"saturday": 240, "sunday": 180})


def test_malformed_limit_falls_back():
    with _with_ini("[limits]\ndefault = lots\nfriday = 60\n"):
        check("malformed default -> built-in", config.get_default_limit(), 120)
        check("valid weekday still applied",
              config.get_weekday_limits(), {"friday": 60})


def test_notification_legacy_thresholds_sorted_desc():
    with _with_ini("[notifications]\nthresholds = 1, 10, 5\nsound_enabled = no\n"):
        n = config.get_notification_settings()
        check("thresholds sorted desc", n["thresholds"], [10, 5, 1])
        check("sound disabled", n["sound_enabled"], False)
        check("legacy: one default sound per mark",
              n["sound_by_minute"], {10: None, 5: None, 1: None})


def test_notification_named_sounds_mapping():
    ini = (
        "[sounds]\n"
        "gentle = /snd/gentle.wav\n"
        "urgent = /snd/urgent.wav\n"
        "[notifications]\n"
        "sound_file = /snd/default.wav\n"
        "notify = 15:gentle, 5:urgent, 1:\n"
    )
    with _with_ini(ini):
        n = config.get_notification_settings()
        check("thresholds from notify keys", n["thresholds"], [15, 5, 1])
        check("named gentle resolved", n["sound_by_minute"][15], "/snd/gentle.wav")
        check("named urgent resolved", n["sound_by_minute"][5], "/snd/urgent.wav")
        # No name on the 1-minute mark -> falls back to the default sound.
        check("missing name -> default", n["sound_by_minute"][1], "/snd/default.wav")
        check("default sound resolved", n["default_sound"], "/snd/default.wav")


def test_notification_unknown_name_falls_back_to_default():
    ini = ("[notifications]\nsound_file = /snd/default.wav\n"
           "notify = 10:nope\n")
    with _with_ini(ini):
        n = config.get_notification_settings()
        check("unknown name -> default", n["sound_by_minute"][10], "/snd/default.wav")


def test_monitoring_csv_parsing():
    ini = "[monitoring]\nmonitored_users = Tommy, Sara\nexempt_users = Dad\n"
    with _with_ini(ini):
        m = config.get_monitoring_settings()
        check("monitored parsed", m["monitored_users"], ["Tommy", "Sara"])
        check("exempt parsed", m["exempt_users"], ["Dad"])
        check("grace default", m["grace_period_seconds"], 60)


def test_chat_settings():
    with _with_ini(None):
        c = config.get_chat_settings()
        check("chat enabled by default", c["enabled"], True)
        check("kid_name empty by default", c["kid_name"], "")
        check("admin popup on by default", c["admin_popup_enabled"], True)
        check("chat sound on by default", c["chat_sound_enabled"], True)
        check("chat_sound none by default", c["chat_sound"], None)
    with _with_ini("[chat]\nenabled = false\nkid_name = Tommy\n"
                   "admin_popup_enabled = false\nchat_sound_enabled = false\n"):
        c = config.get_chat_settings()
        check("chat can be disabled", c["enabled"], False)
        check("kid_name read", c["kid_name"], "Tommy")
        check("admin popup off", c["admin_popup_enabled"], False)
        check("chat sound off", c["chat_sound_enabled"], False)


def test_chat_sound_name_and_path():
    # A [sounds] name resolves to its mapped file.
    with _with_ini("[sounds]\nping = /snd/ping.wav\n[chat]\nchat_sound = ping\n"):
        c = config.get_chat_settings()
        check("chat_sound by name", c["chat_sound"], "/snd/ping.wav")
    # A bare path is used as-is (absolute) — no [sounds] entry needed.
    with _with_ini("[chat]\nchat_sound = /snd/other.wav\n"):
        c = config.get_chat_settings()
        check("chat_sound by path", c["chat_sound"], "/snd/other.wav")


def test_db_path_relative_resolves_to_repo_root():
    with _with_ini("[storage]\ndb_path = data/k.db\n"):
        path = config.get_db_path()
        check("relative db path is absolute", os.path.isabs(path), True)
        check("relative db path ends right", path.endswith(os.path.join("data", "k.db")), True)


def main():
    tests = [
        test_defaults_when_no_file,
        test_web_overrides,
        test_per_weekday_limits,
        test_malformed_limit_falls_back,
        test_notification_legacy_thresholds_sorted_desc,
        test_notification_named_sounds_mapping,
        test_notification_unknown_name_falls_back_to_default,
        test_monitoring_csv_parsing,
        test_chat_settings,
        test_chat_sound_name_and_path,
        test_db_path_relative_resolves_to_repo_root,
    ]
    original = config.CONFIG_PATH
    try:
        for t in tests:
            print(t.__name__)
            t()
    finally:
        config.CONFIG_PATH = original
    print("\nAll config tests passed.")


if __name__ == "__main__":
    main()
