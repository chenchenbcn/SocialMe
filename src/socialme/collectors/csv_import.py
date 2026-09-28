"""Import data exported manually from any platform's native analytics (LinkedIn, X, or any
platform/metric the APIs do not expose).

Config:
    platform: linkedin            # any label
    posts_csv: exports/linkedin_posts.csv
    countries_csv: exports/linkedin_countries.csv   # optional: columns country, views
    followers_total: 12500         # optional, or followers_csv with columns date, followers_total, new_followers
    new_followers: 340             # optional

Column names are matched case-insensitively against the aliases below, so most native
exports work after at most renaming a header.
"""

from __future__ import annotations

import csv
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from ..countries import country_name
from ..models import AccountSnapshot, CollectionResult, Post
from .base import Collector, in_period, parse_datetime, to_int

ALIASES = {
    "post_id": ["post_id", "id", "video id", "post id", "content id", "update id"],
    "published_at": ["published_at", "date", "publish time", "published", "created", "post time",
                     "created date", "publish date", "time"],
    "title": ["title", "caption", "description", "post title", "text", "update title", "video title"],
    "url": ["url", "link", "permalink", "post link", "video link"],
    "media_type": ["media_type", "type", "post type", "content type"],
    "views": ["views", "video views", "impressions", "plays", "total play"],
    "likes": ["likes", "reactions", "total likes"],
    "shares": ["shares", "reposts", "retweets", "total shares"],
    "comments": ["comments", "replies", "total comments"],
    "country": ["country", "country name", "territory", "location", "geography"],
    "followers_total": ["followers_total", "followers", "total followers"],
    "new_followers": ["new_followers", "new followers", "followers gained", "follows"],
}


def _resolve(headers: List[str], key: str) -> Optional[str]:
    lowered = {h.strip().lower(): h for h in headers}
    for alias in ALIASES[key]:
        if alias in lowered:
            return lowered[alias]
    return None


def _read(path: str) -> List[Dict[str, str]]:
    with open(Path(path).expanduser(), newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


class CsvCollector(Collector):
    def __init__(self, config, http=None):
        super().__init__(config, http)
        self.platform = config.get("platform", "csv")
        self.account = config.get("name") or self.platform

    def collect(self, start: date, end: date) -> CollectionResult:
        warnings: List[str] = []
        posts: List[Post] = []
        if self.config.get("posts_csv"):
            rows = _read(self.config["posts_csv"])
            headers = list(rows[0].keys()) if rows else []
            col = {k: _resolve(headers, k) for k in
                   ("post_id", "published_at", "title", "url", "media_type", "views", "likes", "shares", "comments")}
            if rows and not col["published_at"]:
                raise ValueError(f"{self.config['posts_csv']}: no date column found (expected one of "
                                 f"{ALIASES['published_at']})")
            for i, row in enumerate(rows):
                get = lambda k: row.get(col[k], "") if col[k] else ""  # noqa: E731
                published = parse_datetime(get("published_at"))
                if not in_period(published, start, end):
                    continue
                posts.append(Post(
                    platform=self.platform, account=self.account,
                    post_id=get("post_id") or get("url") or f"row-{i + 2}", published_at=published,
                    title=get("title")[:200], url=get("url"), media_type=get("media_type"),
                    views=to_int(get("views")), likes=to_int(get("likes")),
                    shares=to_int(get("shares")), comments=to_int(get("comments")),
                ))

        views_by_country: Dict[str, int] = {}
        if self.config.get("countries_csv"):
            rows = _read(self.config["countries_csv"])
            headers = list(rows[0].keys()) if rows else []
            c_col, v_col = _resolve(headers, "country"), _resolve(headers, "views")
            for row in rows:
                name = country_name(row[c_col])
                views_by_country[name] = views_by_country.get(name, 0) + (to_int(row[v_col]) or 0)

        followers_total = to_int(self.config.get("followers_total"))
        new_followers = to_int(self.config.get("new_followers"))
        if self.config.get("followers_csv"):
            rows = _read(self.config["followers_csv"])
            headers = list(rows[0].keys()) if rows else []
            d_col = _resolve(headers, "published_at")
            t_col, n_col = _resolve(headers, "followers_total"), _resolve(headers, "new_followers")
            rows = [r for r in rows if not d_col or in_period(parse_datetime(r[d_col]), start, end)]
            if rows and t_col:
                followers_total = to_int(rows[-1][t_col])
            if rows and n_col:
                new_followers = sum(to_int(r[n_col]) or 0 for r in rows)

        snapshot = AccountSnapshot(
            platform=self.platform, account=self.account, captured_at=datetime.now(timezone.utc),
            followers_total=followers_total, new_followers=new_followers, views_by_country=views_by_country,
        )
        return CollectionResult(self.platform, self.account, start, end, snapshot, posts, warnings)
