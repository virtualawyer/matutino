"""SQLite state: settings, feeds, issues, and which stories ran when.

The database lives in the data folder, which must be a real Linux
filesystem -- never the exFAT media drive (no file locking there).
"""

import json
import os
import sqlite3
import threading
import time

from .sections import DEFAULT as DEFAULT_SECTIONS


def _system_zone():
    """The container's TZ if it names a real zone, else UTC."""
    name = os.environ.get("TZ", "")
    try:
        from zoneinfo import ZoneInfo
        ZoneInfo(name)
        return name
    except Exception:
        return "UTC"


DEFAULTS = {
    "paper_name": "The Morning Paper",
    "edition": "Morning Edition",
    "build_time": "05:15",
    "timezone": _system_zone(),
    "schedule_on": True,
    "per_feed": 5,
    "lookback_hours": 36,
    "keep_days": 14,
    "language": "en",
    "sections": DEFAULT_SECTIONS,
    "section_labels": {},  # section -> the name it prints under, set at the desk ("World News = Mundo")
    "weather_on": True,
    "weather_place": "",
    "weather_lat": None,
    "weather_lon": None,
    "onthisday_on": True,
    "browser_ua": False,
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS feeds (
  id INTEGER PRIMARY KEY, position INTEGER NOT NULL, section TEXT NOT NULL,
  name TEXT NOT NULL DEFAULT '', url TEXT NOT NULL UNIQUE, mode TEXT NOT NULL DEFAULT 'full',
  last_status TEXT NOT NULL DEFAULT '', last_error TEXT NOT NULL DEFAULT '',
  last_count INTEGER NOT NULL DEFAULT 0, last_checked REAL NOT NULL DEFAULT 0,
  added REAL NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS seen (key TEXT PRIMARY KEY, issue_date TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS seen_date ON seen(issue_date);
CREATE TABLE IF NOT EXISTS issues (
  date TEXT PRIMARY KEY, number INTEGER NOT NULL, built_at REAL NOT NULL,
  stories INTEGER NOT NULL, report TEXT NOT NULL DEFAULT '{}');
"""


class DB(object):
    def __init__(self, path):
        self.conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.conn.executescript(SCHEMA)
            cols = [r[1] for r in self.conn.execute("PRAGMA table_info(feeds)")]
            if "added" not in cols:
                self.conn.execute("ALTER TABLE feeds ADD COLUMN added REAL NOT NULL DEFAULT 0")

    def q(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    def x(self, sql, args=()):
        with self.lock:
            return self.conn.execute(sql, args)

    # settings --------------------------------------------------------------
    def settings(self):
        s = json.loads(json.dumps(DEFAULTS))  # deep copy: the section list is mutable
        for r in self.q("SELECT key, value FROM settings"):
            if r["key"] in DEFAULTS:
                s[r["key"]] = json.loads(r["value"])
        return s

    def save_settings(self, values):
        with self.lock:
            for k, v in values.items():
                if k in DEFAULTS:
                    self.x("INSERT OR REPLACE INTO settings VALUES (?, ?)", (k, json.dumps(v)))

    def get(self, key, default=None):
        r = self.q("SELECT value FROM settings WHERE key = ?", (key,))
        return json.loads(r[0]["value"]) if r else default

    def put(self, key, value):
        self.x("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, json.dumps(value)))

    # feeds -----------------------------------------------------------------
    def feeds(self):
        return self.q("SELECT * FROM feeds ORDER BY position, id")

    def feed_by_url(self, url):
        r = self.q("SELECT * FROM feeds WHERE url = ?", (url,))
        return r[0] if r else None

    def add_feed(self, section, name, url, mode):
        with self.lock:
            pos = self.q("SELECT COALESCE(MAX(position), 0) + 1 AS p FROM feeds")[0]["p"]
            # Keep a section's feeds together: slot a new feed in after the
            # last one already in its section.
            same = self.q("SELECT MAX(position) AS p FROM feeds WHERE section = ?", (section,))
            if same and same[0]["p"] is not None:
                pos = same[0]["p"] + 1
                self.x("UPDATE feeds SET position = position + 1 WHERE position >= ?", (pos,))
            cur = self.x("INSERT INTO feeds (position, section, name, url, mode, added) VALUES (?,?,?,?,?,?)",
                         (pos, section, name, url, mode, time.time()))
            return cur.lastrowid

    def update_feed(self, fid, **fields):
        allowed = {"section", "name", "mode", "position", "last_status", "last_error",
                   "last_count", "last_checked"}
        sets = [(k, v) for k, v in fields.items() if k in allowed]
        if sets:
            self.x("UPDATE feeds SET %s WHERE id = ?" % ", ".join("%s = ?" % k for k, _ in sets),
                   tuple(v for _, v in sets) + (fid,))

    def delete_feed(self, fid):
        self.x("DELETE FROM feeds WHERE id = ?", (fid,))

    # issues ----------------------------------------------------------------
    def issues(self):
        return self.q("SELECT date, number, built_at, stories FROM issues ORDER BY date DESC")

    def issue(self, date):
        r = self.q("SELECT * FROM issues WHERE date = ?", (date,))
        return r[0] if r else None

    def next_number(self, date):
        r = self.issue(date)
        if r:
            return r["number"]
        return self.q("SELECT COALESCE(MAX(number), 0) + 1 AS n FROM issues")[0]["n"]

    def record_issue(self, date, number, stories, report):
        self.x("INSERT OR REPLACE INTO issues VALUES (?,?,?,?,?)",
               (date, number, time.time(), stories, json.dumps(report)))

    def drop_issue(self, date):
        self.x("DELETE FROM issues WHERE date = ?", (date,))

    # seen ------------------------------------------------------------------
    def previous_build(self, date):
        """When the last issue before `date` was printed, or None."""
        r = self.q("SELECT built_at FROM issues WHERE date < ? ORDER BY date DESC LIMIT 1", (date,))
        return r[0]["built_at"] if r else None

    def seen_on(self, date):
        return set(r["key"] for r in self.q("SELECT key FROM seen WHERE issue_date = ?", (date,)))

    def seen_before(self, date):
        """Story keys that ran in an issue earlier than `date`.

        Keys from `date` itself are excluded so rebuilding today's issue
        reprints today's stories instead of finding nothing new.
        """
        return set(r["key"] for r in self.q("SELECT key FROM seen WHERE issue_date < ?", (date,)))

    def mark_seen(self, date, keys):
        with self.lock:
            self.x("BEGIN")
            try:
                self.x("DELETE FROM seen WHERE issue_date = ?", (date,))
                self.conn.executemany("INSERT OR IGNORE INTO seen VALUES (?, ?)",
                                      [(k, date) for k in keys])
                self.x("COMMIT")
            except Exception:
                self.x("ROLLBACK")
                raise

    def prune_seen(self, before_date):
        self.x("DELETE FROM seen WHERE issue_date < ?", (before_date,))
