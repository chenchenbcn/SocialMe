"""Platform-independent data model shared by every collector."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, List, Optional


@dataclass
class Post:
    """A single publication (post, reel, video, short...)."""

    platform: str
    account: str
    post_id: str
    published_at: datetime
    title: str = ""
    url: str = ""
    media_type: str = ""
    views: Optional[int] = None
    likes: Optional[int] = None
    shares: Optional[int] = None
    comments: Optional[int] = None


@dataclass
class AccountSnapshot:
    """Account-level numbers for the reporting period."""

    platform: str
    account: str
    captured_at: datetime
    followers_total: Optional[int] = None
    # Followers gained during the period, when the platform reports it directly.
    # When None, it is derived from previously stored snapshots (see storage.py).
    new_followers: Optional[int] = None
    # Views per country for the period: {"Spain": 1200, "Mexico": 800, ...}
    # Some platforms only expose reach/audience by country; see README.
    views_by_country: Dict[str, int] = field(default_factory=dict)
    country_metric: str = "views"


@dataclass
class CollectionResult:
    platform: str
    account: str
    period_start: date
    period_end: date
    snapshot: AccountSnapshot
    posts: List[Post] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
