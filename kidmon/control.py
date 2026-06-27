"""Time-enforcement engine for Kid PC Monitor.

This is the platform-agnostic port of the old ``pc_control.PCTimeControl``. It
keeps the exact, unit-tested enforcement behaviour (usage accounting, the
once-per-day save session, crossing-based countdown warnings) but:

* all OS actions go through a :class:`~kidmon.platform.base.PlatformOps` backend
  instead of ctypes/tkinter, so it runs on Windows and Linux;
* persistence is in SQLite (:class:`~kidmon.storage.Storage`) instead of a JSON
  file, which also gives us per-day usage history;
* the daily allowance auto-applies from config per weekday, and the parent can
  override it for the current day;
* warnings play a configurable sound (and an optional popup) instead of a
  mandatory on-screen dialog;
* a background sampler logs the foreground program for the activity history.

The Flask app (``kidmon.web``) calls the public ``set_*``/``clear_*``/``lock_now``
/``status``/``send_message`` methods; the monitor and activity threads run the
enforcement and sampling loops.
"""
import logging
import threading
import time
from datetime import datetime, time as dtime, timedelta

from .usage_logic import usage_minutes
from .warning_logic import (
    warnings_to_send, initial_remaining_notice, format_remaining_message,
)
from .grace_logic import (
    decide_grace_action, RESET, NONE, LOCK_NOW, GRANT_SESSION, RELOCK,
)
from .schedule_logic import limit_for_weekday
from .notification_logic import select_sound

logger = logging.getLogger("kidmon.control")


class TimeControl:
    def __init__(self, platform, storage, config):
        """
        Args:
            platform: a PlatformOps backend (lock / is_locked / sound / ...).
            storage:  a Storage instance for state, history and activity.
            config:   the kidmon.config module (or any object exposing the same
                      get_* helpers); injected so tests can substitute it.
        """
        self.platform = platform
        self.storage = storage
        self.config = config

        mon = config.get_monitoring_settings()
        self.monitored_users = mon["monitored_users"]
        self.exempt_users = mon["exempt_users"]
        self.grace_period_seconds = mon["grace_period_seconds"]

        self.notif = config.get_notification_settings()
        self.warning_intervals = self.notif["thresholds"]
        self.sound_by_minute = self.notif["sound_by_minute"]
        self.default_sound = self.notif["default_sound"]

        self.activity = config.get_activity_settings()

        self.current_user = platform.current_user()

        chat = config.get_chat_settings()
        self.chat_enabled = chat["enabled"]
        # Friendly display name for the kid (header + chat); falls back to the
        # OS account name. The kid can't change it (it's server-side config).
        self.kid_name = chat["kid_name"] or self.current_user

        # Live enforcement state (guarded by state_lock). The server/web threads
        # mutate limit/start_time/warnings while the monitor thread reads them.
        self.state_lock = threading.RLock()
        self.usage_limit = None        # today's effective limit (minutes) or None
        self.limit_day = None          # ISO date the usage_limit applies to
        self.lock_times = []           # list[datetime.time]
        self.start_time = datetime.now()
        self.locked_accumulated = timedelta(0)
        self.lock_started_at = None

        self.is_locked = False
        self.warnings_sent = set()
        self.last_remaining = None

        # Once-per-day post-lock save session.
        self.over_limit_locked = False
        self.grace_deadline = None
        self.grace_used_date = None

        if self.should_monitor_user():
            logger.info("Monitoring enabled for user: %s", self.current_user)
        else:
            logger.info("User %s is EXEMPT from monitoring", self.current_user)

        self.load_state()
        self._apply_daily_limit_if_new_day()

    # --- user scope ----------------------------------------------------------

    def should_monitor_user(self):
        if self.monitored_users:
            return self.current_user in self.monitored_users
        if self.exempt_users:
            return self.current_user not in self.exempt_users
        return True

    # --- persistence ---------------------------------------------------------

    def load_state(self):
        """Restore live state from the SQLite state table, if present."""
        try:
            s = self.storage
            today = datetime.now().date()

            lock_times = s.get_state("lock_times")
            if lock_times:
                self.lock_times = [dtime(*map(int, t.split(":")))
                                   for t in lock_times]

            self.usage_limit = s.get_state("usage_limit")
            limit_day = s.get_state("limit_day")
            self.limit_day = (datetime.fromisoformat(limit_day).date()
                              if limit_day else None)

            start_time = s.get_state("start_time")
            if start_time:
                saved = datetime.fromisoformat(start_time)
                if saved.date() < today:
                    self.start_time = datetime.now()
                    logger.info("Start time was from %s, reset to today",
                                saved.date())
                else:
                    self.start_time = saved
                    banked = s.get_state("locked_accumulated")
                    if banked is not None:
                        self.locked_accumulated = timedelta(seconds=banked)

            grace_used = s.get_state("grace_used_date")
            if grace_used:
                d = datetime.fromisoformat(grace_used).date()
                if d >= today:
                    self.grace_used_date = d

            logger.info("State loaded: %d lock times, usage limit: %s",
                        len(self.lock_times), self.usage_limit)
        except Exception as e:
            logger.error("Error loading state: %s", e)

    def save_state(self):
        try:
            self.storage.set_state_many({
                "lock_times": [f"{lt.hour}:{lt.minute}" for lt in self.lock_times],
                "usage_limit": self.usage_limit,
                "limit_day": self.limit_day.isoformat() if self.limit_day else None,
                "start_time": self.start_time.isoformat(),
                "locked_accumulated": self.locked_accumulated.total_seconds(),
                "grace_used_date": (self.grace_used_date.isoformat()
                                    if self.grace_used_date else None),
            })
        except Exception as e:
            logger.error("Error saving state: %s", e)

    # --- daily allowance -----------------------------------------------------

    def _apply_daily_limit_if_new_day(self):
        """At a day rollover, apply the configured allowance for the new day.

        The parent's same-day override (set via set_usage_limit) holds until the
        next day, when the configured per-weekday allowance auto-applies again
        and the usage clock resets.
        """
        today = datetime.now().date()
        with self.state_lock:
            if self.limit_day == today:
                return
            per_day = self.config.get_weekday_limits()
            default = self.config.get_default_limit()
            self.usage_limit = limit_for_weekday(today.weekday(), per_day, default)
            self.limit_day = today
            self.reset_usage_clock()
            self.warnings_sent.clear()
            self.last_remaining = None
            self.grace_used_date = None
            self.over_limit_locked = False
            self.grace_deadline = None
        logger.info("Applied daily limit for %s: %s minutes",
                    today, self.usage_limit)
        self.save_state()

    def reset_usage_clock(self):
        """Start the usage period fresh from now. Call while holding state_lock."""
        self.start_time = datetime.now()
        self.locked_accumulated = timedelta(0)
        if self.lock_started_at is not None:
            self.lock_started_at = self.start_time

    # --- live screen-lock tracking ------------------------------------------

    def monitor_lock_state(self):
        """Track real lock/unlock so locked time is excluded from the limit."""
        while True:
            try:
                actual_locked = self.platform.is_locked()
                with self.state_lock:
                    if actual_locked and self.lock_started_at is None:
                        self.lock_started_at = datetime.now()
                    elif not actual_locked and self.lock_started_at is not None:
                        self.locked_accumulated += datetime.now() - self.lock_started_at
                        self.lock_started_at = None

                if self.is_locked and not actual_locked:
                    self.is_locked = False
                    logger.info("PC unlocked (detected)")
                elif not self.is_locked and actual_locked:
                    logger.info("PC locked (detected)")
            except Exception as e:
                logger.error("lock-state monitor error: %s", e)
            time.sleep(3)

    # --- enforcement primitives ---------------------------------------------

    def lock_pc(self):
        self.is_locked = True
        self.platform.lock()
        logger.info("PC locked")

    def alert(self, message, sound_path=None):
        """Notify the kid: per-threshold sound, optional on-screen popup.

        ``sound_path`` is the resolved wav for this specific alert; when None the
        configured default sound (or a system beep) is used.
        """
        if self.notif["sound_enabled"]:
            self.platform.play_sound(sound_path or self.default_sound)
        if self.notif["popup_enabled"]:
            self.platform.notify("Computer time", message)
        logger.info("Alert: %s", message)

    def add_scheduled_lock(self, hour, minute):
        self.lock_times.append(dtime(hour, minute))

    def set_usage_limit(self, minutes):
        """Parent override for today: set the limit and restart the clock."""
        with self.state_lock:
            self.usage_limit = minutes
            self.limit_day = datetime.now().date()
            self.reset_usage_clock()
            self.warnings_sent.clear()
            self.last_remaining = None
            self.over_limit_locked = False
            self.grace_deadline = None
        self.save_state()

    def extend_time(self, minutes):
        with self.state_lock:
            if self.usage_limit is None:
                return False
            self.usage_limit += minutes
            self.warnings_sent.clear()
            self.last_remaining = None
        self.save_state()
        return True

    def clear_usage_limit(self):
        with self.state_lock:
            self.usage_limit = None
            self.warnings_sent.clear()
            self.last_remaining = None
        self.save_state()

    def clear_lock_times(self):
        with self.state_lock:
            self.lock_times = []
            self.warnings_sent.clear()
            self.last_remaining = None
        self.save_state()

    def clear_all(self):
        with self.state_lock:
            self.usage_limit = None
            self.lock_times = []
            self.warnings_sent.clear()
            self.last_remaining = None
        self.save_state()

    def send_message(self, body, sender="parent"):
        """Admin quick-popup: show a message on the kid's screen and store it."""
        self.platform.notify("Message from parent", body)
        self.storage.add_message(datetime.now().isoformat(), sender, body, "Parent")

    def post_chat(self, body, is_parent, parent_name=None):
        """Post a chat message. Role is decided by the caller from the session.

        Parent messages also pop up on the kid's screen (popup only, no sound);
        kid replies are stored only — the parent sees them on their own device.
        Returns the stored message dict, or None for an empty body.
        """
        body = body.strip()[:500]
        if not body:
            return None
        if is_parent:
            sender, name = "parent", (parent_name or "Parent").strip()[:40] or "Parent"
        else:
            sender, name = "kid", self.kid_name
        ts = datetime.now().isoformat()
        self.storage.add_message(ts, sender, body, name)
        if is_parent:
            self.platform.notify(f"Message from {name}", body)
        return {"ts": ts, "sender": sender, "name": name, "body": body}

    # --- remaining time + warnings ------------------------------------------

    def get_time_remaining(self):
        """Minutes until the soonest lock (usage or schedule). None = no limit."""
        if not self.should_monitor_user():
            return None
        now = datetime.now()
        min_remaining = None

        with self.state_lock:
            lock_times = list(self.lock_times)
            usage_limit = self.usage_limit
            start_time = self.start_time
            locked_accumulated = self.locked_accumulated
            lock_started_at = self.lock_started_at

        for lt in lock_times:
            when = now.replace(hour=lt.hour, minute=lt.minute,
                               second=0, microsecond=0)
            if when <= now:
                when += timedelta(days=1)
            minutes = (when - now).total_seconds() / 60
            if min_remaining is None or minutes < min_remaining:
                min_remaining = minutes

        if usage_limit is not None:
            used = usage_minutes(now, start_time, locked_accumulated, lock_started_at)
            until_limit = usage_limit - used
            if min_remaining is None or until_limit < min_remaining:
                min_remaining = until_limit

        if min_remaining is not None and min_remaining < 0:
            min_remaining = 0
        return min_remaining

    def check_and_send_warnings(self):
        remaining = self.get_time_remaining()
        if remaining is None:
            self.last_remaining = None
            return

        previous = self.last_remaining
        self.last_remaining = remaining

        notice = initial_remaining_notice(previous, remaining, self.warning_intervals)
        if notice is not None:
            sound = select_sound(notice, self.warning_intervals,
                                 self.sound_by_minute, self.default_sound)
            self.alert(format_remaining_message(notice), sound)

        for mins in warnings_to_send(previous, remaining,
                                     self.warning_intervals, self.warnings_sent):
            self.warnings_sent.add(mins)
            unit = "minute" if mins == 1 else "minutes"
            sound = self.sound_by_minute.get(mins) or self.default_sound
            self.alert(f"Computer will lock in {mins} {unit}!", sound)

    # --- limit checks + enforcement -----------------------------------------

    def check_time_limits(self):
        if not self.should_monitor_user():
            return False, ""
        now = datetime.now()
        with self.state_lock:
            lock_times = list(self.lock_times)
            usage_limit = self.usage_limit
            start_time = self.start_time
            locked_accumulated = self.locked_accumulated
            lock_started_at = self.lock_started_at

        for lt in lock_times:
            if now.hour == lt.hour and now.minute == lt.minute:
                return True, "Scheduled lock time reached"

        if usage_limit is not None:
            used = usage_minutes(now, start_time, locked_accumulated, lock_started_at)
            if used >= usage_limit:
                return True, f"Usage limit of {usage_limit} minutes reached"
        return False, ""

    def enforce(self, should_lock, reason):
        """One enforcement tick, including the once-per-day save session."""
        now = datetime.now()
        with self.state_lock:
            action = decide_grace_action(
                now, should_lock, self.is_locked, self.over_limit_locked,
                self.grace_deadline, self.grace_used_date,
                self.grace_period_seconds)
            if action == RESET:
                self.over_limit_locked = False
                self.grace_deadline = None
            elif action == GRANT_SESSION:
                self.grace_deadline = now + timedelta(seconds=self.grace_period_seconds)
                self.grace_used_date = now.date()
                self.over_limit_locked = True
            elif action in (LOCK_NOW, RELOCK):
                self.over_limit_locked = True
                self.grace_deadline = None

        if action == LOCK_NOW:
            logger.info("Locking PC: %s", reason)
            self.lock_pc()
        elif action == RELOCK:
            logger.info("Re-locking PC: save time is up")
            self.lock_pc()
        elif action == GRANT_SESSION:
            self.save_state()
            secs = self.grace_period_seconds
            window = (f"{secs // 60} minute(s)"
                      if secs >= 60 and secs % 60 == 0 else f"{secs} seconds")
            # Use the most urgent configured sound (the smallest threshold).
            urgent = select_sound(0, self.warning_intervals,
                                  self.sound_by_minute, self.default_sound)
            self.alert(f"You're out of time. Save your work now — the PC will "
                       f"lock in {window}. This is your one save chance today.",
                       urgent)
            logger.info("Granted the one-per-day save session")

    # --- background loops ----------------------------------------------------

    def run_monitor(self):
        """Main enforcement loop. Runs forever; never exits after a lock."""
        logger.info("Time control running")
        last_history = 0.0
        while True:
            try:
                self._apply_daily_limit_if_new_day()
                self.check_and_send_warnings()
                should_lock, reason = self.check_time_limits()
                self.enforce(should_lock, reason)

                # Persist usage history roughly every 30s for the admin page.
                now = time.time()
                if now - last_history >= 30:
                    self._record_history()
                    last_history = now
            except Exception as e:
                logger.error("Monitor loop error: %s", e)
            time.sleep(1)

    def _record_history(self):
        with self.state_lock:
            usage_limit = self.usage_limit
            used = usage_minutes(datetime.now(), self.start_time,
                                 self.locked_accumulated, self.lock_started_at)
        self.storage.record_daily_usage(
            datetime.now().date().isoformat(), used * 60, usage_limit)

    def run_activity_sampler(self):
        """Log the foreground program at a fixed interval for the history."""
        if not self.activity["enabled"]:
            return
        interval = max(5, self.activity["interval_seconds"])
        logger.info("Activity sampler running (every %ss)", interval)
        while True:
            try:
                if self.should_monitor_user() and not self.platform.is_locked():
                    app = self.platform.foreground_app()
                    if app is not None:
                        process, title = app
                        self.storage.log_activity(
                            datetime.now().isoformat(), process, title, interval)
            except Exception as e:
                logger.error("Activity sampler error: %s", e)
            time.sleep(interval)

    def start_threads(self):
        """Start the lock-state, enforcement and activity threads (daemons)."""
        threading.Thread(target=self.monitor_lock_state, daemon=True).start()
        threading.Thread(target=self.run_monitor, daemon=True).start()
        threading.Thread(target=self.run_activity_sampler, daemon=True).start()

    # --- status for the web UI ----------------------------------------------

    def status(self):
        """Read-only summary for the kid page and admin dashboard."""
        monitored = self.should_monitor_user()
        remaining = self.get_time_remaining() if monitored else None

        next_lock = None
        soonest = None
        now = datetime.now()
        for lt in self.lock_times:
            when = now.replace(hour=lt.hour, minute=lt.minute,
                               second=0, microsecond=0)
            if when <= now:
                when += timedelta(days=1)
            if soonest is None or when < soonest:
                soonest = when
                next_lock = f"{lt.hour:02d}:{lt.minute:02d}"

        return {
            "user": self.kid_name,
            "monitored": monitored,
            "is_locked": self.is_locked,
            "time_remaining": int(remaining) if remaining is not None else None,
            "usage_limit": self.usage_limit,
            "lock_times": [f"{lt.hour:02d}:{lt.minute:02d}" for lt in self.lock_times],
            "next_lock": next_lock,
        }
