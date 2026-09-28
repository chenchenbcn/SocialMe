"""TikTok via the TikTok API for Business (Accounts API, v1.3).

Config: business_id, access_token, [account_fields], [video_fields]

Views by country is computed from each video's `audience_countries`
(share of that video's viewers per country) x video_views.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from ..countries import country_name
from ..models import AccountSnapshot, CollectionResult, Post
from .base import ApiError, Collector, in_period, parse_datetime, to_int

BASE = "https://business-api.tiktok.com/open_api/v1.3"
DEFAULT_ACCOUNT_FIELDS = ["username", "display_name", "followers_count", "daily_new_followers"]
DEFAULT_VIDEO_FIELDS = ["item_id", "create_time", "caption", "share_url", "video_views",
                        "likes", "comments", "shares", "audience_countries"]


class TikTokCollector(Collector):
    platform = "tiktok"

    def _get(self, path: str, **params) -> Dict[str, Any]:
        params = {k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in params.items()}
        data = self.http.get(f"{BASE}/{path}", headers={"Access-Token": self.config["access_token"]}, params=params)
        if data.get("code", 0) != 0:
            raise ApiError(f"TikTok {path}: {data.get('code')} {data.get('message')}")
        return data.get("data", {})

    def collect(self, start: date, end: date) -> CollectionResult:
        business_id = self.config["business_id"]
        warnings: List[str] = []

        account = self._get("business/get/", business_id=business_id,
                            start_date=start.isoformat(), end_date=end.isoformat(),
                            fields=self.config.get("account_fields", DEFAULT_ACCOUNT_FIELDS))
        metrics = sorted(account.get("metrics") or [], key=lambda m: m.get("date", ""))
        new_followers: Optional[int] = None
        if metrics and any("daily_new_followers" in m for m in metrics):
            new_followers = sum(to_int(m.get("daily_new_followers")) or 0 for m in metrics)
        elif not metrics:
            warnings.append("TikTok returned no daily metrics; new followers will come from stored snapshots")

        posts: List[Post] = []
        views_by_country: Dict[str, float] = {}
        cursor = None
        while True:
            params = {"business_id": business_id, "max_count": 20,
                      "fields": self.config.get("video_fields", DEFAULT_VIDEO_FIELDS)}
            if cursor is not None:
                params["cursor"] = cursor
            data = self._get("business/video/list/", **params)
            reached_older = False
            for v in data.get("videos", []):
                created = v.get("create_time")
                published = parse_datetime(to_int(created) if str(created).isdigit() else created)
                if published.date() < start:
                    reached_older = True
                    continue
                if not in_period(published, start, end):
                    continue
                views = to_int(v.get("video_views"))
                posts.append(Post(
                    platform=self.platform, account=self.account, post_id=str(v.get("item_id")),
                    published_at=published, title=(v.get("caption") or "")[:200],
                    url=v.get("share_url", ""), media_type="video", views=views,
                    likes=to_int(v.get("likes")), comments=to_int(v.get("comments")),
                    shares=to_int(v.get("shares")),
                ))
                for c in v.get("audience_countries") or []:
                    name = country_name(c.get("country", ""))
                    views_by_country[name] = views_by_country.get(name, 0) + (views or 0) * float(c.get("percentage") or 0)
            cursor = data.get("cursor")
            if reached_older or not data.get("has_more"):
                break

        snapshot = AccountSnapshot(
            platform=self.platform, account=self.account, captured_at=datetime.now(timezone.utc),
            followers_total=to_int(account.get("followers_count")), new_followers=new_followers,
            views_by_country={k: round(v) for k, v in views_by_country.items()},
            country_metric="views (estimated from per-video audience share)",
        )
        return CollectionResult(self.platform, self.account, start, end, snapshot, posts, warnings)
