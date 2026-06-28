"""The OS abstraction interface for Kid PC Monitor.

Everything the agent does that is operating-system specific goes through this
small interface, so the enforcement logic in ``kidmon.control`` stays platform
agnostic. Concrete backends live in ``windows.py`` and ``linux.py`` and are
selected by ``kidmon.platform.get_platform()``.

The interface is deliberately tiny — five capabilities:

* ``current_user``        — the logged-in account name (for monitor/exempt).
* ``is_locked``           — is the screen currently at the lock prompt?
* ``lock``                — lock the screen now.
* ``foreground_app``      — (process_name, window_title) of the active window,
                            or None if it can't be determined.
* ``play_sound`` / ``notify`` — best-effort notifications (a sound, a popup).

Notification methods must never raise: a failure to beep should not disturb
enforcement. Backends log and swallow their own errors.
"""


class PlatformOps:
    """Abstract OS operations. Subclasses implement every method."""

    def current_user(self):
        raise NotImplementedError

    def is_locked(self):
        raise NotImplementedError

    def lock(self):
        raise NotImplementedError

    def foreground_app(self):
        """Return (process_name, window_title) or None if unavailable."""
        raise NotImplementedError

    def play_sound(self, path=None):
        """Play a sound file, or a default system sound when path is empty.

        ``.wav`` always works; other formats (mp3, opus, ogg, …) need a
        general-purpose player (ffplay/mpv) on PATH — see ``audio.py``.
        """
        raise NotImplementedError

    def notify(self, title, message):
        """Show a non-blocking on-screen notification (best effort)."""
        raise NotImplementedError
