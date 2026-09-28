"""SQLite history of every run, so follower growth can be derived when an API does not report it."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from .models import CollectionResult

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    platform TEXT, account TEXT, captured_at TEXT, period_start TEXT, period_end TEXT,
    followers_total INTEGER, new_followers INTEGER
);
CREATE TABLE IF NOT EXISTS posts (
    platform TEXT, account TEXT, post_id TEXT, published_at TEXT, title TEXT, url TEXT,
    media_type TEXT, views INTEGER, likes INTEGER, shares INTEGER, comments INTEGER, updated_at TEXT,
    PRIMARY KEY (platform, account, post_id)
);
CREATE TABLE IF NOT EXISTS country_views (
    platform TEXT, account TEXT, period_start TEXT, period_end TEXT, country TEXT, views INTEGER,
    PRIMARY KEY (platform, account, period_start, period_end, country)
);
"""


class Store:
    def __init__(self, path: str):
        Path(path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(Path(path).expanduser()))
        self.conn.executescript(SCHEMA)

    def previous_followers(self, platform: str, account: str, before: str) -> Optional[int]:
        row = self.conn.execute(
            "SELECT followers_total FROM snapshots WHERE platform=? AND account=? AND captured_at<? "
            "AND followers_total IS NOT NULL ORDER BY captured_at DESC LIMIT 1",
            (platform, account, before)).fetchone()
        return row[0] if row else None

    def fill_new_followers(self, result: CollectionResult) -> None:
        """If the platform gave no 'new followers', use the difference with the last stored total."""
        snap = result.snapshot
        if snap.new_followers is not None or snap.followers_total is None:
            return
        prev = self.previous_followers(snap.platform, snap.account, snap.captured_at.isoformat())
        if prev is not None:
            snap.new_followers = snap.followers_total - prev
            result.warnings.append("new followers = followers now - followers at previous run")

    def save(self, result: CollectionResult) -> None:
        snap = result.snapshot
        with self.conn:
            self.conn.execute(
                "INSERT INTO snapshots VALUES (?,?,?,?,?,?,?)",
                (snap.platform, snap.account, snap.captured_at.isoformat(), result.period_start.isoformat(),
                 result.period_end.isoformat(), snap.followers_total, snap.new_followers))
            now = snap.captured_at.isoformat()
            self.conn.executemany(
                "INSERT OR REPLACE INTO posts VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                [(p.platform, p.account, p.post_id, p.published_at.isoformat(), p.title, p.url, p.media_type,
                  p.views, p.likes, p.shares, p.comments, now) for p in result.posts])
            self.conn.executemany(
                "INSERT OR REPLACE INTO country_views VALUES (?,?,?,?,?,?)",
                [(snap.platform, snap.account, result.period_start.isoformat(), result.period_end.isoformat(),
                  c, v) for c, v in snap.views_by_country.items()])
