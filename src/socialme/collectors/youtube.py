"""YouTube: Data API v3 (videos, stats, subscribers) + Analytics API (shares, new subs, countries).

Config:
    client_id, client_secret, refresh_token  (OAuth with scopes youtube.readonly
                                               and yt-analytics.readonly)
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Dict, List

from ..countries import country_name
from ..models import AccountSnapshot, CollectionResult, Post
from .base import ApiError, Collector, in_period, parse_datetime, to_int

TOKEN_URL = "https://oauth2.googleapis.com/token"
DATA_API = "https://www.googleapis.com/youtube/v3"
ANALYTICS_API = "https://youtubeanalytics.googleapis.com/v2/reports"


class YouTubeCollector(Collector):
    platform = "youtube"

    def _token(self) -> str:
        if self.config.get("access_token"):
            return self.config["access_token"]
        data = self.http.post(TOKEN_URL, data={
            "client_id": self.config["client_id"],
            "client_secret": self.config["client_secret"],
            "refresh_token": self.config["refresh_token"],
            "grant_type": "refresh_token",
        })
        return data["access_token"]

    def collect(self, start: date, end: date) -> CollectionResult:
        headers = {"Authorization": f"Bearer {self._token()}"}
        warnings: List[str] = []

        channel = self.http.get(f"{DATA_API}/channels", headers=headers,
                                params={"part": "statistics,contentDetails,snippet", "mine": "true"})
        items = channel.get("items") or []
        if not items:
            raise ApiError("YouTube: no channel found for these credentials")
        ch = items[0]
        uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]

        video_ids = self._video_ids_in_period(headers, uploads, start, end)
        posts = self._videos(headers, video_ids)

        try:
            shares = self._shares(headers, video_ids, end)
            for p in posts:
                p.shares = shares.get(p.post_id, 0)
        except ApiError as exc:
            warnings.append(f"shares unavailable: {exc}")

        report_params = {"ids": "channel==MINE", "startDate": start.isoformat(), "endDate": end.isoformat()}
        new_followers = None
        try:
            subs = self.http.get(ANALYTICS_API, headers=headers,
                                 params={**report_params, "metrics": "subscribersGained"})
            rows = subs.get("rows") or []
            new_followers = to_int(rows[0][0]) if rows else 0
        except ApiError as exc:
            warnings.append(f"subscribersGained unavailable: {exc}")

        views_by_country: Dict[str, int] = {}
        try:
            geo = self.http.get(ANALYTICS_API, headers=headers, params={
                **report_params, "metrics": "views", "dimensions": "country", "sort": "-views"})
            for code, views in geo.get("rows") or []:
                views_by_country[country_name(code)] = to_int(views) or 0
        except ApiError as exc:
            warnings.append(f"views by country unavailable: {exc}")

        snapshot = AccountSnapshot(
            platform=self.platform, account=self.account, captured_at=datetime.now(timezone.utc),
            followers_total=to_int(ch.get("statistics", {}).get("subscriberCount")),
            new_followers=new_followers, views_by_country=views_by_country,
        )
        return CollectionResult(self.platform, self.account, start, end, snapshot, posts, warnings)

    def _video_ids_in_period(self, headers, playlist_id: str, start: date, end: date) -> List[str]:
        ids: List[str] = []
        page_token = None
        while True:
            params = {"part": "contentDetails", "playlistId": playlist_id, "maxResults": 50}
            if page_token:
                params["pageToken"] = page_token
            data = self.http.get(f"{DATA_API}/playlistItems", headers=headers, params=params)
            reached_older = False
            for item in data.get("items", []):
                details = item["contentDetails"]
                published = parse_datetime(details.get("videoPublishedAt") or item.get("snippet", {}).get("publishedAt"))
                if in_period(published, start, end):
                    ids.append(details["videoId"])
                elif published.date() < start:
                    reached_older = True
            page_token = data.get("nextPageToken")
            if reached_older or not page_token:
                return ids

    def _videos(self, headers, video_ids: List[str]) -> List[Post]:
        posts: List[Post] = []
        for i in range(0, len(video_ids), 50):
            data = self.http.get(f"{DATA_API}/videos", headers=headers, params={
                "part": "snippet,statistics", "id": ",".join(video_ids[i:i + 50])})
            for v in data.get("items", []):
                stats = v.get("statistics", {})
                posts.append(Post(
                    platform=self.platform, account=self.account, post_id=v["id"],
                    published_at=parse_datetime(v["snippet"]["publishedAt"]),
                    title=v["snippet"].get("title", ""),
                    url=f"https://www.youtube.com/watch?v={v['id']}", media_type="video",
                    views=to_int(stats.get("viewCount")), likes=to_int(stats.get("likeCount")),
                    comments=to_int(stats.get("commentCount")),
                ))
        return posts

    def _shares(self, headers, video_ids: List[str], end: date) -> Dict[str, int]:
        """Lifetime shares per video (shares only exist in the Analytics API)."""
        shares: Dict[str, int] = {}
        for i in range(0, len(video_ids), 50):
            data = self.http.get(ANALYTICS_API, headers=headers, params={
                "ids": "channel==MINE", "startDate": "2005-04-23",
                "endDate": max(end, date.today()).isoformat(),
                "metrics": "shares", "dimensions": "video",
                "filters": "video==" + ",".join(video_ids[i:i + 50]),
            })
            for vid, value in data.get("rows") or []:
                shares[vid] = to_int(value) or 0
        return shares
