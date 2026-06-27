"""SQLite persistence for Kid PC Monitor.

Holds everything that must survive a restart or accumulate over time:

* ``state``        — a small key/value store (JSON values) for the live
                     enforcement snapshot (start time, banked locked time,
                     today's limit override, scheduled lock times, grace guard).
                     This replaces the old ``pc_control_state.json`` file.
* ``daily_usage``  — one row per day: minutes used and the limit in force, so
                     the admin page can show a usage history.
* ``activity``     — a log of foreground programs sampled over time.
* ``messages``     — parent/kid messages (groundwork for a future chat; written
                     by the admin "send message" action today).

A single connection is shared across the monitor, activity and web threads, so
all access is serialised behind one lock. SQLite with ``check_same_thread`` off
plus our own lock is sufficient for this low write rate.
"""
import json
import sqlite3
import threading
from datetime import date


_SCHEMA = """
CREATE TABLE IF NOT EXISTS state (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS daily_usage (
    day           TEXT PRIMARY KEY,   -- ISO date
    used_seconds  REAL NOT NULL DEFAULT 0,
    limit_minutes INTEGER             -- NULL = no limit that day
);
CREATE TABLE IF NOT EXISTS activity (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT NOT NULL,            -- ISO datetime
    day     TEXT NOT NULL,            -- ISO date (for cheap per-day rollups)
    process TEXT,
    title   TEXT,
    seconds REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_activity_day ON activity(day);
CREATE TABLE IF NOT EXISTS messages (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    ts     TEXT NOT NULL,
    sender TEXT NOT NULL,             -- 'parent' or 'kid'
    name   TEXT,                      -- display name (e.g. 'Mom', 'Tommy')
    body   TEXT NOT NULL,
    seen   INTEGER NOT NULL DEFAULT 0
);
"""

# Keep at most this many chat messages; older ones are pruned on insert so the
# database can't grow without bound over a long deployment.
_MESSAGE_RETENTION = 1000


class Storage:
    def __init__(self, db_path):
        self.db_path = db_path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._migrate()
            self._conn.commit()

    def _migrate(self):
        """Apply small in-place schema upgrades for databases created earlier."""
        cols = {r["name"] for r in
                self._conn.execute("PRAGMA table_info(messages)").fetchall()}
        if "name" not in cols:
            self._conn.execute("ALTER TABLE messages ADD COLUMN name TEXT")

    def close(self):
        with self._lock:
            self._conn.close()

    # --- state key/value -----------------------------------------------------

    def get_state(self, key, default=None):
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM state WHERE key = ?", (key,)).fetchone()
        if row is None:
            return default
        return json.loads(row["value"])

    def set_state(self, key, value):
        payload = json.dumps(value)
        with self._lock:
            self._conn.execute(
                "INSERT INTO state(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, payload))
            self._conn.commit()

    def set_state_many(self, mapping):
        """Persist several state keys atomically (one transaction)."""
        with self._lock:
            for key, value in mapping.items():
                self._conn.execute(
                    "INSERT INTO state(key, value) VALUES(?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, json.dumps(value)))
            self._conn.commit()

    # --- daily usage history -------------------------------------------------

    def record_daily_usage(self, day, used_seconds, limit_minutes):
        """Upsert the usage row for a day (ISO date string)."""
        with self._lock:
            self._conn.execute(
                "INSERT INTO daily_usage(day, used_seconds, limit_minutes) "
                "VALUES(?, ?, ?) ON CONFLICT(day) DO UPDATE SET "
                "used_seconds = excluded.used_seconds, "
                "limit_minutes = excluded.limit_minutes",
                (day, used_seconds, limit_minutes))
            self._conn.commit()

    def get_history(self, limit=30):
        """Return recent daily-usage rows, newest first."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT day, used_seconds, limit_minutes FROM daily_usage "
                "ORDER BY day DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    # --- activity log --------------------------------------------------------

    def log_activity(self, ts, process, title, seconds):
        day = ts[:10]  # ISO datetime -> ISO date
        with self._lock:
            self._conn.execute(
                "INSERT INTO activity(ts, day, process, title, seconds) "
                "VALUES(?, ?, ?, ?, ?)", (ts, day, process, title, seconds))
            self._conn.commit()

    def get_activity_summary(self, day=None, limit=20):
        """Top programs by total seconds for a day (default: today)."""
        if day is None:
            day = date.today().isoformat()
        with self._lock:
            rows = self._conn.execute(
                "SELECT process, SUM(seconds) AS total FROM activity "
                "WHERE day = ? AND process IS NOT NULL "
                "GROUP BY process ORDER BY total DESC LIMIT ?",
                (day, limit)).fetchall()
        return [dict(r) for r in rows]

    # --- messages (chat groundwork) -----------------------------------------

    def add_message(self, ts, sender, body, name=None):
        with self._lock:
            self._conn.execute(
                "INSERT INTO messages(ts, sender, name, body) VALUES(?, ?, ?, ?)",
                (ts, sender, name, body))
            # Prune oldest beyond the retention cap.
            self._conn.execute(
                "DELETE FROM messages WHERE id NOT IN "
                "(SELECT id FROM messages ORDER BY id DESC LIMIT ?)",
                (_MESSAGE_RETENTION,))
            self._conn.commit()

    def get_messages(self, limit=50):
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, ts, sender, name, body, seen FROM messages "
                "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in reversed(rows)]
