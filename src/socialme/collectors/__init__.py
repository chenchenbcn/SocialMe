from .base import Collector
from .csv_import import CsvCollector
from .meta import FacebookCollector, InstagramCollector
from .tiktok import TikTokCollector
from .youtube import YouTubeCollector

COLLECTORS = {
    "youtube": YouTubeCollector,
    "instagram": InstagramCollector,
    "facebook": FacebookCollector,
    "tiktok": TikTokCollector,
    "csv": CsvCollector,
}


def build_collector(source: dict) -> Collector:
    kind = source.get("type")
    if kind not in COLLECTORS:
        raise ValueError(f"Unknown source type {kind!r}; expected one of {sorted(COLLECTORS)}")
    return COLLECTORS[kind](source)
