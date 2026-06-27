"""Unit tests for the shared port configuration (src/config.py).

Pure and dependency-free: run with `python tests/test_config.py` (or via
pytest). No tkinter / Flask / Windows needed. Each test points
config.CONFIG_PATH at a throwaway temp file, so the real repo config.ini is
never read or written.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import config  # noqa: E402


def check(name, got, want):
    assert got == want, f"{name}: expected {want!r}, got {got!r}"
    print(f"  ok: {name}")


def _with_ini(contents):
    """Point config at a fresh temp config.ini; None means 'no file'.

    Returns the temp directory (caller keeps it alive until done).
    """
    tmp = tempfile.TemporaryDirectory()
    path = os.path.join(tmp.name, "config.ini")
    if contents is not None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(contents)
    config.CONFIG_PATH = path
    return tmp


def test_defaults_when_no_file():
    with _with_ini(None):
        check("no file -> defaults", config.get_ports(),
              {"agent": 9999, "web_panel": 5000, "kid_status_page": 8080})


def test_override_from_ini():
    with _with_ini("[ports]\nagent = 12345\nweb_panel = 5050\n"):
        ports = config.get_ports()
        check("agent overridden", ports["agent"], 12345)
        check("web_panel overridden", ports["web_panel"], 5050)
        check("kid_status_page default kept", ports["kid_status_page"], 8080)


def test_kid_page_disabled_values():
    for raw in ("none", "off", "disabled", "0", ""):
        with _with_ini(f"[ports]\nkid_status_page = {raw}\n"):
            check(f"kid_status_page='{raw}' -> None",
                  config.get_ports()["kid_status_page"], None)


def test_malformed_value_falls_back():
    with _with_ini("[ports]\nagent = not_a_number\nweb_panel = 6000\n"):
        ports = config.get_ports()
        check("malformed agent -> default", ports["agent"], 9999)
        check("valid web_panel still applied", ports["web_panel"], 6000)


def test_missing_section_uses_defaults():
    with _with_ini("[something_else]\nfoo = bar\n"):
        check("no [ports] section -> defaults", config.get_ports(),
              {"agent": 9999, "web_panel": 5000, "kid_status_page": 8080})


def test_write_ports_creates_and_merges():
    with _with_ini(None):
        path = config.write_ports(agent=22222)
        check("file created", os.path.exists(path), True)
        ports = config.get_ports()
        check("written agent applied", ports["agent"], 22222)
        check("others preserved as defaults", ports["web_panel"], 5000)


def test_write_ports_roundtrips_disable():
    with _with_ini(None):
        config.write_ports(kid_status_page=None)
        check("None written as disabled", config.get_ports()["kid_status_page"], None)


def test_write_ports_rejects_unknown_key():
    with _with_ini(None):
        try:
            config.write_ports(bogus=1)
        except KeyError:
            print("  ok: unknown key rejected")
        else:
            raise AssertionError("expected KeyError for unknown port key")


def main():
    tests = [
        test_defaults_when_no_file,
        test_override_from_ini,
        test_kid_page_disabled_values,
        test_malformed_value_falls_back,
        test_missing_section_uses_defaults,
        test_write_ports_creates_and_merges,
        test_write_ports_roundtrips_disable,
        test_write_ports_rejects_unknown_key,
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
