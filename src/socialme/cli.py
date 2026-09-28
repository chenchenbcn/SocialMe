"""Command line entry point: `socialme collect --config config.yaml --period last-month`."""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from datetime import date, timedelta
from typing import Tuple

import yaml

from .analytics import TOP_COUNTRIES_THRESHOLD
from .collectors import build_collector
from .report import write_reports
from .storage import Store

log = logging.getLogger("socialme")


def load_dotenv(path: str = ".env") -> None:
    """Minimal .env support: KEY=value lines, never overriding variables already set."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_config(path: str) -> dict:
    """Load YAML config, expanding ${ENV_VAR} references so secrets can stay out of the file."""
    load_dotenv()
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    text = re.sub(r"\$\{(\w+)\}", lambda m: os.environ.get(m.group(1), ""), text)
    return yaml.safe_load(text) or {}


def resolve_period(period: str, today: date) -> Tuple[date, date]:
    if period == "last-week":  # previous Monday..Sunday
        start = today - timedelta(days=today.weekday() + 7)
        return start, start + timedelta(days=6)
    if period == "this-week":
        return today - timedelta(days=today.weekday()), today
    if period == "last-month":
        end = today.replace(day=1) - timedelta(days=1)
        return end.replace(day=1), end
    if period == "this-month":
        return today.replace(day=1), today
    m = re.fullmatch(r"last-(\d+)-days", period)
    if m:
        return today - timedelta(days=int(m.group(1))), today - timedelta(days=1)
    raise ValueError(f"Unknown period {period!r}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="socialme", description="Collect social media account analytics")
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("collect", help="collect data and write the report")
    c.add_argument("--config", default="config.yaml")
    c.add_argument("--period", default="last-month",
                   help="last-week | this-week | last-month | this-month | last-N-days")
    c.add_argument("--start", type=date.fromisoformat, help="YYYY-MM-DD (overrides --period)")
    c.add_argument("--end", type=date.fromisoformat, help="YYYY-MM-DD (overrides --period)")
    c.add_argument("--out", help="output directory (default: config 'output_dir' or ./reports)")
    c.add_argument("--only", nargs="*", help="only these account names")
    c.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")
    config = load_config(args.config)
    start, end = resolve_period(args.period, date.today())
    if args.start or args.end:
        start, end = args.start or start, args.end or end

    store = Store(config.get("database", "data/socialme.db"))
    threshold = float(config.get("top_countries_threshold", TOP_COUNTRIES_THRESHOLD))
    results, failed = [], 0
    for source in config.get("accounts", []):
        name = source.get("name") or source.get("type")
        if args.only and name not in args.only:
            continue
        log.info("Collecting %s (%s) %s..%s", name, source.get("type"), start, end)
        try:
            result = build_collector(source).collect(start, end)
        except Exception as exc:  # keep going with the other accounts
            failed += 1
            log.error("  %s failed: %s", name, exc)
            continue
        store.fill_new_followers(result)
        store.save(result)
        for w in result.warnings:
            log.warning("  %s: %s", name, w)
        log.info("  %d publications, %s followers", len(result.posts), result.snapshot.followers_total)
        results.append(result)

    if not results:
        log.error("No data collected")
        return 1
    path = write_reports(results, args.out or config.get("output_dir", "reports"), threshold)
    log.info("Report written to %s", path)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
