"""Shared collector plumbing: HTTP with retries and the Collector interface."""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from datetime import date, datetime, timezone
from typing import Any, Dict, Optional

import requests

from ..models import CollectionResult

log = logging.getLogger(__name__)


class ApiError(RuntimeError):
    pass


class HttpClient:
    def __init__(self, session: Optional[requests.Session] = None, retries: int = 3, timeout: int = 30):
        self.session = session or requests.Session()
        self.retries = retries
        self.timeout = timeout

    def request(self, method: str, url: str, **kwargs) -> Dict[str, Any]:
        kwargs.setdefault("timeout", self.timeout)
        for attempt in range(self.retries + 1):
            resp = self.session.request(method, url, **kwargs)
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < self.retries:
                time.sleep(2 ** attempt)
                continue
            try:
                data = resp.json()
            except ValueError:
                data = {}
            if resp.status_code >= 400:
                raise ApiError(f"{method} {url} -> HTTP {resp.status_code}: {data or resp.text[:300]}")
            return data
        raise ApiError(f"{method} {url} failed after {self.retries} retries")

    def get(self, url: str, **kwargs) -> Dict[str, Any]:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> Dict[str, Any]:
        return self.request("POST", url, **kwargs)


class Collector(ABC):
    platform: str = ""

    def __init__(self, config: Dict[str, Any], http: Optional[HttpClient] = None):
        self.config = config
        self.account = config.get("name") or self.platform
        self.http = http or HttpClient()

    @abstractmethod
    def collect(self, start: date, end: date) -> CollectionResult:
        """Collect posts published in [start, end] and account metrics for that period."""


def parse_datetime(value: Any) -> datetime:
    """Parse ISO-8601 strings (incl. Meta's +0000 offsets) or unix timestamps to aware UTC."""
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    text = str(value).strip().replace("Z", "+00:00")
    if len(text) >= 5 and text[-5] in "+-" and text[-3] != ":":
        text = text[:-2] + ":" + text[-2:]
    dt = datetime.fromisoformat(text)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def in_period(dt: datetime, start: date, end: date) -> bool:
    return start <= dt.date() <= end


def to_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(float(str(value).replace(",", "")))
    except ValueError:
        return None
