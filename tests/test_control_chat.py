"""Tests for how a parent chat message reaches the kid PC.

The split: an admin-panel "send message" pops up on the kid's screen (when
admin_popup_enabled); a message typed in the chat window only plays a sound
(when chat_sound_enabled), never a popup. Kid replies do neither on the kid PC.

Run directly (``python tests/test_control_chat.py``) or under pytest. Each test
points config.CONFIG_PATH at a throwaway file and uses a fake platform that
records its notify/play_sound calls instead of touching the OS.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kidmon import config  # noqa: E402
from kidmon.control import TimeControl  # noqa: E402
from kidmon.platform.base import PlatformOps  # noqa: E402
from kidmon.storage import Storage  # noqa: E402


def check(label, got, expected):
    status = "ok" if got == expected else "FAIL"
    print(f"  [{status}] {label}: {got!r}")
    assert got == expected, f"{label}: expected {expected!r}, got {got!r}"


class FakePlatform(PlatformOps):
    def __init__(self):
        self.notifications = []
        self.sounds = []

    def current_user(self):
        return "Tommy"

    def is_locked(self):
        return False

    def lock(self):
        pass

    def foreground_app(self):
        return None

    def play_sound(self, path=None):
        self.sounds.append(path)

    def notify(self, title, message):
        self.notifications.append((title, message))


def _control(ini):
    tmp = tempfile.TemporaryDirectory()
    config.CONFIG_PATH = os.path.join(tmp.name, "config.ini")
    if ini:
        with open(config.CONFIG_PATH, "w", encoding="utf-8") as f:
            f.write(ini)
    storage = Storage(os.path.join(tmp.name, "k.db"))
    platform = FakePlatform()
    return TimeControl(platform, storage, config), platform, tmp


def test_admin_message_pops_up_no_sound():
    control, plat, tmp = _control(None)
    try:
        control.post_chat("Dinner!", is_parent=True, parent_name="Dad",
                          announce="admin")
        check("admin message pops up", len(plat.notifications), 1)
        check("popup titled by sender", plat.notifications[0][0],
              "Message from Dad")
        check("admin message plays no sound", plat.sounds, [])
    finally:
        tmp.cleanup()


def test_chat_message_plays_sound_no_popup():
    control, plat, tmp = _control(None)
    try:
        control.post_chat("hi", is_parent=True, parent_name="Mom")
        check("chat message plays a sound", len(plat.sounds), 1)
        check("default chat sound is system beep", plat.sounds[0], None)
        check("chat message shows no popup", plat.notifications, [])
    finally:
        tmp.cleanup()


def test_chat_sound_uses_configured_file():
    ini = "[chat]\nchat_sound = /snd/ping.wav\n"
    control, plat, tmp = _control(ini)
    try:
        control.post_chat("hi", is_parent=True, parent_name="Mom")
        check("chat plays the configured sound", plat.sounds, ["/snd/ping.wav"])
    finally:
        tmp.cleanup()


def test_settings_can_disable_both_channels():
    ini = ("[chat]\nadmin_popup_enabled = false\nchat_sound_enabled = false\n")
    control, plat, tmp = _control(ini)
    try:
        control.post_chat("a", is_parent=True, parent_name="Dad",
                          announce="admin")
        control.post_chat("b", is_parent=True, parent_name="Dad")
        check("admin popup suppressed", plat.notifications, [])
        check("chat sound suppressed", plat.sounds, [])
    finally:
        tmp.cleanup()


def test_kid_reply_is_silent_on_kid_pc():
    control, plat, tmp = _control(None)
    try:
        control.post_chat("ok mom", is_parent=False)
        check("kid reply no popup", plat.notifications, [])
        check("kid reply no sound", plat.sounds, [])
    finally:
        tmp.cleanup()


def main():
    tests = [
        test_admin_message_pops_up_no_sound,
        test_chat_message_plays_sound_no_popup,
        test_chat_sound_uses_configured_file,
        test_settings_can_disable_both_channels,
        test_kid_reply_is_silent_on_kid_pc,
    ]
    original = config.CONFIG_PATH
    try:
        for t in tests:
            print(t.__name__)
            t()
    finally:
        config.CONFIG_PATH = original
    print("\nAll control-chat tests passed.")


if __name__ == "__main__":
    main()
