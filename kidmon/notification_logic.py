"""Pure logic for per-threshold notification sounds.

The parent configures named sounds once in ``[sounds]`` and then maps each
minutes-remaining mark to a name in ``[notifications] notify`` — e.g.::

    [sounds]
    gentle = /home/kid/gentle.wav
    urgent = /home/kid/urgent.wav

    [notifications]
    notify = 15:gentle, 5:urgent, 1:urgent

This module is dependency-free (no config / file I/O): it parses the ``notify``
string and, given a remaining time, selects which sound to play. Path resolution
(name -> file) is done in ``kidmon.config``; here we only deal with minutes,
names and an already-resolved minute->path map. Unit-tested in
tests/test_notification_logic.py.
"""


def parse_notify(notify_str):
    """Parse a ``notify`` value into ``[(minute, name_or_None), ...]``.

    Accepts ``"15:gentle, 5:urgent, 1:"`` style input. Each entry is
    ``minute:name``; an empty/missing name means "alert at this minute but use
    the default sound". Malformed entries (non-integer minute) are skipped. The
    result is sorted by minute descending, and a later entry for the same minute
    overrides an earlier one.
    """
    pairs = {}
    for item in notify_str.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" in item:
            minute_part, name_part = item.split(":", 1)
            name = name_part.strip() or None
        else:
            minute_part, name = item, None
        minute_part = minute_part.strip()
        try:
            minute = int(minute_part)
        except ValueError:
            continue
        pairs[minute] = name
    return [(m, pairs[m]) for m in sorted(pairs, reverse=True)]


def select_sound(remaining, thresholds, sound_by_minute, default=None):
    """Pick the sound to play for a given remaining time (minutes).

    The chosen mark is the smallest threshold that is still at or above
    ``remaining`` — i.e. the mark the kid has most recently reached. When called
    with an exact threshold value, that resolves to the same threshold. Returns
    that mark's configured sound, or ``default`` when the mark has no specific
    sound or no mark applies (e.g. above the largest threshold).
    """
    candidates = [m for m in thresholds if m >= remaining]
    if not candidates:
        return default
    sound = sound_by_minute.get(min(candidates))
    return sound if sound else default
