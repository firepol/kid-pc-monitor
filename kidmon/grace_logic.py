"""Pure decision logic for the once-per-day post-lock save session.

Kept free of tkinter / ctypes / file I/O so it can be unit-tested on any
platform. See docs/add-grace-period.md for the behaviour this implements.
"""

# Actions returned by decide_grace_action:
RESET = "reset"                  # back under the limit: clear the episode state
NONE = "none"                    # nothing to do this tick
LOCK_NOW = "lock_now"            # first time over the limit: the normal immediate lock
GRANT_SESSION = "grant_session"  # kid's one allowed save login: warn and start the window
RELOCK = "relock"                # save window expired (or none left today): lock again


def decide_grace_action(now, should_lock, is_locked, over_limit_locked,
                        grace_deadline, grace_used_date, grace_period_seconds):
    """Decide what the enforcement loop should do this tick.

    Args:
        now: current datetime.
        should_lock: True if a usage/scheduled limit is currently exceeded.
        is_locked: True if the screen is currently locked.
        over_limit_locked: True if we already locked for this over-limit episode.
        grace_deadline: datetime the active save session ends, or None.
        grace_used_date: date the one-per-day save session was consumed, or None.
        grace_period_seconds: length of the save session; <= 0 disables it.

    Returns one of RESET / NONE / LOCK_NOW / GRANT_SESSION / RELOCK.
    """
    if not should_lock:
        # No longer over any limit: the over-limit episode is finished.
        return RESET

    if is_locked:
        # Already at the lock screen. Only act if a save window somehow outlived
        # a lock and has now expired (safety net; normally the kid is unlocked
        # during a save window).
        if grace_deadline is not None and now >= grace_deadline:
            return RELOCK
        return NONE

    # Over the limit and the screen is unlocked.
    if not over_limit_locked:
        # First time over the limit this episode: lock immediately, as before.
        # The save session is the *re-login* that comes after this lock.
        return LOCK_NOW

    # The kid has logged back in after the initial lock.
    if grace_deadline is not None:
        # A save session is running: let them keep saving until it expires.
        return RELOCK if now >= grace_deadline else NONE

    # No session running yet: grant the one allowed save session per day,
    # otherwise re-lock immediately.
    if grace_period_seconds > 0 and grace_used_date != now.date():
        return GRANT_SESSION
    return RELOCK
