"""Write the collected data to an Excel workbook plus CSV files."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import List

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from .analytics import TOP_COUNTRIES_THRESHOLD, engagement_totals, publications_per_period, top_countries
from .models import CollectionResult

POST_COLUMNS = ["platform", "account", "published_at", "title", "media_type", "views", "likes",
                "shares", "comments", "url", "post_id"]


def summary_rows(results: List[CollectionResult], threshold: float = TOP_COUNTRIES_THRESHOLD) -> List[list]:
    rows = []
    for r in results:
        totals = engagement_totals(r.posts)
        days = (r.period_end - r.period_start).days + 1
        top = top_countries(r.snapshot.views_by_country, threshold)
        rows.append([
            r.platform, r.account, r.period_start.isoformat(), r.period_end.isoformat(),
            totals["posts"], round(totals["posts"] / days * 7, 2),
            totals["views"], totals["likes"], totals["shares"], totals["comments"],
            r.snapshot.followers_total, r.snapshot.new_followers,
            ", ".join(c for c, _, _ in top),
            round(sum(s for _, _, s in top) * 100, 1) if top else None,
            r.snapshot.country_metric if top else "",
            " | ".join(r.warnings),
        ])
    return rows


SUMMARY_HEADER = ["platform", "account", "period_start", "period_end", "publications",
                  "publications_per_week", "views", "likes", "shares", "comments", "followers_total",
                  "new_followers", "top_countries_60pct", "top_countries_share_%", "country_metric", "notes"]


def write_reports(results: List[CollectionResult], out_dir: str,
                  threshold: float = TOP_COUNTRIES_THRESHOLD) -> Path:
    out = Path(out_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    start = min(r.period_start for r in results).isoformat()
    end = max(r.period_end for r in results).isoformat()
    stem = f"social_report_{start}_{end}"
    all_posts = [p for r in results for p in r.posts]
    periods = publications_per_period(all_posts)

    sheets = {
        "Summary": (SUMMARY_HEADER, summary_rows(results, threshold)),
        "Posts": (POST_COLUMNS, [
            [p.platform, p.account, p.published_at.strftime("%Y-%m-%d %H:%M"), p.title, p.media_type,
             p.views, p.likes, p.shares, p.comments, p.url, p.post_id]
            for p in sorted(all_posts, key=lambda p: (p.platform, p.account, p.published_at))]),
        "Weekly publications": (["platform", "account", "iso_week", "publications"],
                                [[*k, v] for k, v in periods["weekly"].items()]),
        "Monthly publications": (["platform", "account", "month", "publications"],
                                 [[*k, v] for k, v in periods["monthly"].items()]),
        "Countries": (["platform", "account", "country", "views", "share_%", "in_top_60pct"], [
            row for r in results for row in _country_rows(r, threshold)]),
    }

    wb = Workbook()
    wb.remove(wb.active)
    header_font, header_fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="305496")
    for name, (header, rows) in sheets.items():
        ws = wb.create_sheet(name)
        ws.append(header)
        for cell in ws[1]:
            cell.font, cell.fill = header_font, header_fill
        for row in rows:
            ws.append(row)
        ws.freeze_panes = "A2"
        for i, h in enumerate(header, start=1):
            width = max([len(str(h))] + [len(str(row[i - 1] or "")) for row in rows[:500]])
            ws.column_dimensions[get_column_letter(i)].width = min(max(width + 2, 10), 60)

        with open(out / f"{stem}_{name.lower().replace(' ', '_')}.csv", "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(header)
            writer.writerows(rows)

    path = out / f"{stem}.xlsx"
    wb.save(path)
    return path


def _country_rows(r: CollectionResult, threshold: float) -> List[list]:
    views = r.snapshot.views_by_country
    total = sum(views.values()) or 1
    top = {c for c, _, _ in top_countries(views, threshold)}
    return [[r.platform, r.account, c, v, round(v / total * 100, 2), "yes" if c in top else ""]
            for c, v in sorted(views.items(), key=lambda kv: -kv[1])]
