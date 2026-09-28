from datetime import date, datetime, timezone

from socialme.analytics import engagement_totals, publications_per_period, top_countries
from socialme.cli import resolve_period
from socialme.models import Post


def _post(day, views=10, platform="youtube"):
    return Post(platform, "acc", f"id{day}", datetime(2026, 8, day, tzinfo=timezone.utc), views=views, likes=1)


def test_top_countries_reach_60_percent():
    views = {"Spain": 500, "Mexico": 400, "United States": 300, "Argentina": 200, "France": 100}
    top = top_countries(views)
    # 500 + 400 = 900 / 1500 = 60%
    assert [c for c, _, _ in top] == ["Spain", "Mexico"]
    assert round(sum(s for _, _, s in top), 2) == 0.60


def test_top_countries_single_dominant_and_empty():
    assert [c for c, _, _ in top_countries({"Spain": 90, "France": 10})] == ["Spain"]
    assert top_countries({}) == []
    assert top_countries({"Spain": 0}) == []


def test_publications_per_week_and_month():
    posts = [_post(3), _post(5), _post(18), _post(31)]
    periods = publications_per_period(posts)
    assert periods["weekly"] == {("youtube", "acc", "2026-W32"): 2,
                                 ("youtube", "acc", "2026-W34"): 1, ("youtube", "acc", "2026-W36"): 1}
    assert periods["monthly"] == {("youtube", "acc", "2026-08"): 4}


def test_engagement_totals_handles_missing_metrics():
    p = _post(1)
    p.shares = None
    assert engagement_totals([p, _post(2, views=5)]) == {"posts": 2, "views": 15, "likes": 2, "shares": 0, "comments": 0}


def test_resolve_period():
    today = date(2026, 9, 28)  # Monday
    assert resolve_period("last-month", today) == (date(2026, 8, 1), date(2026, 8, 31))
    assert resolve_period("last-week", today) == (date(2026, 9, 21), date(2026, 9, 27))
    assert resolve_period("last-7-days", today) == (date(2026, 9, 21), date(2026, 9, 27))
