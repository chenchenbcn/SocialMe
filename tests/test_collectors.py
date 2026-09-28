"""Collectors tested against canned API responses (no network)."""

from datetime import date
from pathlib import Path

import pytest

from socialme.collectors.base import ApiError
from socialme.collectors.csv_import import CsvCollector
from socialme.collectors.meta import FacebookCollector, InstagramCollector
from socialme.collectors.tiktok import TikTokCollector
from socialme.collectors.youtube import YouTubeCollector

FIXTURES = Path(__file__).parent / "fixtures"
START, END = date(2026, 8, 1), date(2026, 8, 31)


class FakeHttp:
    """Returns the first canned response whose key is a substring of the URL (+ metric param)."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def _match(self, url, params):
        self.calls.append((url, params))
        key = url + "|" + str((params or {}).get("metric") or (params or {}).get("metrics", "")) + "|" + str((params or {}).get("dimensions", ""))
        for pattern, response in self.routes:
            if pattern in key:
                if isinstance(response, Exception):
                    raise response
                return response(params) if callable(response) else response
        raise AssertionError(f"unexpected request {key}")

    def get(self, url, params=None, **kw):
        return self._match(url, params)

    def post(self, url, data=None, **kw):
        return self._match(url, data)


def test_csv_collector():
    result = CsvCollector({"platform": "linkedin", "posts_csv": str(FIXTURES / "posts.csv"),
                           "countries_csv": str(FIXTURES / "countries.csv"),
                           "followers_total": 1000, "new_followers": 50}).collect(START, END)
    assert [p.title for p in result.posts] == ["Launch video", "Behind the scenes", "Tutorial"]
    assert result.posts[0].views == 1200 and result.posts[0].url == "https://example.com/1"
    assert result.snapshot.views_by_country["Spain"] == 500
    assert result.snapshot.views_by_country["Argentina"] == 200
    assert result.snapshot.followers_total == 1000 and result.snapshot.new_followers == 50


def test_youtube_collector():
    http = FakeHttp([
        ("oauth2", {"access_token": "tok"}),
        ("/channels", {"items": [{"statistics": {"subscriberCount": "5000"},
                                  "contentDetails": {"relatedPlaylists": {"uploads": "UU1"}}}]}),
        ("/playlistItems", {"items": [
            {"contentDetails": {"videoId": "v2", "videoPublishedAt": "2026-09-02T10:00:00Z"}},
            {"contentDetails": {"videoId": "v1", "videoPublishedAt": "2026-08-10T10:00:00Z"}},
            {"contentDetails": {"videoId": "v0", "videoPublishedAt": "2026-07-10T10:00:00Z"}},
        ], "nextPageToken": "never-followed"}),
        ("/videos", {"items": [{"id": "v1", "snippet": {"publishedAt": "2026-08-10T10:00:00Z", "title": "Hi"},
                                "statistics": {"viewCount": "900", "likeCount": "80", "commentCount": "7"}}]}),
        ("reports|shares|video", {"rows": [["v1", 12]]}),
        ("reports|subscribersGained|", {"rows": [[42]]}),
        ("reports|views|country", {"rows": [["ES", 600], ["MX", 300], ["US", 100]]}),
    ])
    r = YouTubeCollector({"name": "yt", "client_id": "a", "client_secret": "b", "refresh_token": "c"},
                         http=http).collect(START, END)
    assert len(r.posts) == 1
    p = r.posts[0]
    assert (p.views, p.likes, p.comments, p.shares) == (900, 80, 7, 12)
    assert r.snapshot.followers_total == 5000 and r.snapshot.new_followers == 42
    assert r.snapshot.views_by_country == {"Spain": 600, "Mexico": 300, "United States": 100}
    assert r.warnings == []


def test_instagram_collector_with_partial_failure():
    media = {"data": [
        {"id": "m2", "timestamp": "2026-08-20T09:00:00+0000", "caption": "Reel", "media_product_type": "REELS",
         "permalink": "https://ig/m2", "like_count": 50, "comments_count": 4},
        {"id": "m1", "timestamp": "2026-07-30T09:00:00+0000", "like_count": 1, "comments_count": 1},
    ]}
    http = FakeHttp([
        ("/media|", media),
        ("m2/insights|views,shares", {"data": [{"name": "views", "total_value": {"value": 3000}},
                                                {"name": "shares", "values": [{"value": 25}]}]}),
        ("|follower_count|", {"data": [{"values": [{"value": 3}, {"value": 4}]}]}),
        ("|reached_audience_demographics|", ApiError("not enough followers")),
        ("/1784|", {"followers_count": 2200}),
    ])
    r = InstagramCollector({"ig_user_id": "1784", "access_token": "t"}, http=http).collect(START, END)
    assert len(r.posts) == 1
    assert (r.posts[0].views, r.posts[0].shares, r.posts[0].likes) == (3000, 25, 50)
    assert r.snapshot.followers_total == 2200
    # Aug has 31 days -> two 30-day windows, each returning 3+4
    assert r.snapshot.new_followers == 14
    assert r.snapshot.views_by_country == {}
    assert any("country" in w for w in r.warnings)


def test_facebook_collector():
    http = FakeHttp([
        ("/published_posts|", {"data": [{"id": "p1", "created_time": "2026-08-12T08:00:00+0000", "message": "Hola",
                                         "shares": {"count": 3}, "comments": {"summary": {"total_count": 2}},
                                         "reactions": {"summary": {"total_count": 20}}}]}),
        ("p1/insights|post_media_view", {"data": [{"name": "post_media_view", "values": [{"value": 700}]}]}),
        ("|page_daily_follows_unique|", {"data": [{"values": [{"value": 5}, {"value": 6}]}]}),
        ("/555|", {"followers_count": 9000}),
    ])
    r = FacebookCollector({"page_id": "555", "access_token": "t"}, http=http).collect(START, END)
    p = r.posts[0]
    assert (p.views, p.likes, p.shares, p.comments) == (700, 20, 3, 2)
    assert r.snapshot.followers_total == 9000 and r.snapshot.new_followers == 11


def test_tiktok_collector_estimates_country_views():
    http = FakeHttp([
        ("business/get/", {"code": 0, "data": {"followers_count": 12000, "metrics": [
            {"date": "2026-08-01", "daily_new_followers": 10}, {"date": "2026-08-02", "daily_new_followers": 15}]}}),
        ("video/list", {"code": 0, "data": {"has_more": False, "videos": [
            {"item_id": "t2", "create_time": 1786000000, "video_views": 1000, "likes": 90, "comments": 9,
             "shares": 8, "audience_countries": [{"country": "ES", "percentage": 0.7},
                                                 {"country": "MX", "percentage": 0.3}]},
            {"item_id": "t1", "create_time": 1780000000, "video_views": 50},
        ]}}),
    ])
    r = TikTokCollector({"business_id": "b", "access_token": "t"}, http=http).collect(START, END)
    assert [p.post_id for p in r.posts] == ["t2"]  # 1786000000 = 2026-08-06
    assert r.snapshot.new_followers == 25 and r.snapshot.followers_total == 12000
    assert r.snapshot.views_by_country == {"Spain": 700, "Mexico": 300}


def test_tiktok_error_code_raises():
    http = FakeHttp([("business/get/", {"code": 40001, "message": "bad token"})])
    with pytest.raises(ApiError):
        TikTokCollector({"business_id": "b", "access_token": "t"}, http=http).collect(START, END)
