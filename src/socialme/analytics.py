"""Aggregations: publications per week/month, totals and top countries."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Dict, Iterable, List, Tuple

from .models import Post

TOP_COUNTRIES_THRESHOLD = 0.60


def week_key(dt: datetime) -> str:
    year, week, _ = dt.isocalendar()
    return f"{year}-W{week:02d}"


def month_key(dt: datetime) -> str:
    return f"{dt.year}-{dt.month:02d}"


def publications_per_period(posts: Iterable[Post]) -> Dict[str, Dict[Tuple[str, str, str], int]]:
    """Count publications per (platform, account, ISO week) and per (platform, account, month)."""
    weekly: Counter = Counter()
    monthly: Counter = Counter()
    for p in posts:
        weekly[(p.platform, p.account, week_key(p.published_at))] += 1
        monthly[(p.platform, p.account, month_key(p.published_at))] += 1
    return {"weekly": dict(sorted(weekly.items())), "monthly": dict(sorted(monthly.items()))}


def engagement_totals(posts: Iterable[Post]) -> Dict[str, int]:
    totals = {"posts": 0, "views": 0, "likes": 0, "shares": 0, "comments": 0}
    for p in posts:
        totals["posts"] += 1
        for metric in ("views", "likes", "shares", "comments"):
            totals[metric] += getattr(p, metric) or 0
    return totals


def top_countries(
    views_by_country: Dict[str, int], threshold: float = TOP_COUNTRIES_THRESHOLD
) -> List[Tuple[str, int, float]]:
    """Smallest set of countries (largest first) whose views reach `threshold` of the total.

    Returns [(country, views, share_of_total), ...].
    """
    total = sum(v for v in views_by_country.values() if v)
    if total <= 0:
        return []
    result = []
    cumulative = 0
    for country, views in sorted(views_by_country.items(), key=lambda kv: (-kv[1], kv[0])):
        if not views:
            continue
        result.append((country, views, views / total))
        cumulative += views
        if cumulative / total >= threshold:
            break
    return result
