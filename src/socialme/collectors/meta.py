"""Instagram (professional account) and Facebook Page via the Meta Graph API.

Instagram config:  ig_user_id, access_token, [api_version], [country_timeframe]
Facebook config:   page_id, access_token (Page token), [api_version],
                   [post_views_metric], [new_followers_metric], [country_metric]
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, Iterator, List, Optional

from ..countries import country_name
from ..models import AccountSnapshot, CollectionResult, Post
from .base import ApiError, Collector, in_period, parse_datetime, to_int

DEFAULT_API_VERSION = "v23.0"


class MetaCollector(Collector):
    def _base(self) -> str:
        return f"https://graph.facebook.com/{self.config.get('api_version', DEFAULT_API_VERSION)}"

    def _get(self, path: str, **params) -> Dict[str, Any]:
        params["access_token"] = self.config["access_token"]
        return self.http.get(f"{self._base()}/{path}", params=params)

    def _paginate(self, path: str, **params) -> Iterator[Dict[str, Any]]:
        data = self._get(path, **params)
        while True:
            yield from data.get("data", [])
            next_url = data.get("paging", {}).get("next")
            if not next_url:
                return
            data = self.http.get(next_url)

    def _insight_values(self, data: Dict[str, Any]) -> Dict[str, int]:
        """Flatten an insights response to {metric_name: value} (lifetime / total_value)."""
        out: Dict[str, int] = {}
        for entry in data.get("data", []):
            if "total_value" in entry:
                out[entry["name"]] = to_int(entry["total_value"].get("value")) or 0
            elif entry.get("values"):
                out[entry["name"]] = to_int(entry["values"][-1].get("value")) or 0
        return out

    def _sum_daily(self, path: str, metric: str, start: date, end: date, max_days: int, **extra) -> int:
        """Sum a period=day insights metric over [start, end], querying in windows of max_days."""
        total = 0
        cursor = start
        while cursor <= end:
            window_end = min(end, cursor + timedelta(days=max_days - 1))
            data = self._get(path, metric=metric, period="day",
                             since=_unix(cursor), until=_unix(window_end + timedelta(days=1)), **extra)
            for entry in data.get("data", []):
                for v in entry.get("values", []):
                    total += to_int(v.get("value")) or 0
            cursor = window_end + timedelta(days=1)
        return total


class InstagramCollector(MetaCollector):
    platform = "instagram"

    def collect(self, start: date, end: date) -> CollectionResult:
        ig = self.config["ig_user_id"]
        warnings: List[str] = []
        profile = self._get(ig, fields="username,followers_count,media_count")

        posts: List[Post] = []
        fields = "id,caption,media_type,media_product_type,permalink,timestamp,like_count,comments_count"
        for m in self._paginate(f"{ig}/media", fields=fields, limit=50):
            published = parse_datetime(m["timestamp"])
            if published.date() < start:
                break  # media are returned newest first
            if not in_period(published, start, end):
                continue
            post = Post(
                platform=self.platform, account=self.account, post_id=m["id"], published_at=published,
                title=(m.get("caption") or "")[:200], url=m.get("permalink", ""),
                media_type=(m.get("media_product_type") or m.get("media_type") or "").lower(),
                likes=to_int(m.get("like_count")), comments=to_int(m.get("comments_count")),
            )
            try:
                ins = self._insight_values(self._get(f"{m['id']}/insights", metric="views,shares"))
                post.views, post.shares = ins.get("views"), ins.get("shares")
            except ApiError as exc:
                warnings.append(f"insights unavailable for media {m['id']}: {exc}")
            posts.append(post)

        new_followers: Optional[int] = None
        try:
            # follower_count (period=day) = new followers per day; only the last 30 days are available.
            new_followers = self._sum_daily(ig, "follower_count", start, end, max_days=30)
        except ApiError as exc:
            warnings.append(f"new followers unavailable (Instagram keeps only 30 days): {exc}")

        views_by_country: Dict[str, int] = {}
        timeframe = self.config.get("country_timeframe", "this_month")
        try:
            data = self._get(ig, metric="reached_audience_demographics", period="lifetime",
                             timeframe=timeframe, metric_type="total_value", breakdown="country")
            for entry in data.get("data", []):
                for bd in entry.get("total_value", {}).get("breakdowns", []):
                    for r in bd.get("results", []):
                        views_by_country[country_name(r["dimension_values"][0])] = to_int(r.get("value")) or 0
        except ApiError as exc:
            warnings.append(f"audience by country unavailable: {exc}")

        snapshot = AccountSnapshot(
            platform=self.platform, account=self.account, captured_at=datetime.now(timezone.utc),
            followers_total=to_int(profile.get("followers_count")), new_followers=new_followers,
            views_by_country=views_by_country, country_metric=f"reached accounts ({timeframe})",
        )
        return CollectionResult(self.platform, self.account, start, end, snapshot, posts, warnings)


class FacebookCollector(MetaCollector):
    platform = "facebook"

    def collect(self, start: date, end: date) -> CollectionResult:
        page = self.config["page_id"]
        warnings: List[str] = []
        profile = self._get(page, fields="name,followers_count,fan_count")
        views_metric = self.config.get("post_views_metric", "post_media_view")

        posts: List[Post] = []
        fields = ("id,message,created_time,permalink_url,status_type,shares,"
                  "comments.summary(true).limit(0),reactions.summary(true).limit(0)")
        for p in self._paginate(f"{page}/published_posts", fields=fields, limit=50,
                                since=_unix(start), until=_unix(end + timedelta(days=1))):
            published = parse_datetime(p["created_time"])
            if not in_period(published, start, end):
                continue
            post = Post(
                platform=self.platform, account=self.account, post_id=p["id"], published_at=published,
                title=(p.get("message") or "")[:200], url=p.get("permalink_url", ""),
                media_type=p.get("status_type", ""),
                likes=to_int(p.get("reactions", {}).get("summary", {}).get("total_count")),
                comments=to_int(p.get("comments", {}).get("summary", {}).get("total_count")),
                shares=to_int(p.get("shares", {}).get("count")) or 0,
            )
            try:
                ins = self._insight_values(self._get(f"{p['id']}/insights", metric=views_metric, period="lifetime"))
                post.views = ins.get(views_metric)
            except ApiError as exc:
                warnings.append(f"views unavailable for post {p['id']}: {exc}")
            posts.append(post)

        new_followers: Optional[int] = None
        try:
            metric = self.config.get("new_followers_metric", "page_daily_follows_unique")
            new_followers = self._sum_daily(page, metric, start, end, max_days=90)
        except ApiError as exc:
            warnings.append(f"new followers unavailable: {exc}")

        views_by_country: Dict[str, int] = {}
        country_metric = self.config.get("country_metric")
        if country_metric:
            try:
                data = self._get(page, metric=country_metric, period=self.config.get("country_period", "lifetime"))
                for entry in data.get("data", []):
                    values = entry.get("values") or [{}]
                    for code, v in (values[-1].get("value") or {}).items():
                        views_by_country[country_name(code)] = to_int(v) or 0
            except ApiError as exc:
                warnings.append(f"{country_metric} unavailable: {exc}")
        else:
            warnings.append("Facebook Graph API has no views-by-country metric for Pages; "
                            "import it from Meta Business Suite with a csv source (see README)")

        snapshot = AccountSnapshot(
            platform=self.platform, account=self.account, captured_at=datetime.now(timezone.utc),
            followers_total=to_int(profile.get("followers_count") or profile.get("fan_count")),
            new_followers=new_followers, views_by_country=views_by_country,
            country_metric=country_metric or "views",
        )
        return CollectionResult(self.platform, self.account, start, end, snapshot, posts, warnings)


def _unix(d: date) -> int:
    return int(datetime.combine(d, time.min, tzinfo=timezone.utc).timestamp())
