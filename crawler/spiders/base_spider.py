"""
crawler/spiders/base_spider.py
───────────────────────────────
Abstract base class for all Bangalore property spiders.
Provides shared utilities: area iteration, price parsing, dedup check.
"""

from __future__ import annotations

import hashlib
import logging
import re
from abc import abstractmethod
from datetime import datetime
from typing import Generator, Iterator, List, Optional

import scrapy

from config.areas import TARGET_AREAS, AreaConfig
from config.settings import config
from crawler.items import GeoPoint, PropertyItem

log = logging.getLogger(__name__)


class BangalorePropertySpider(scrapy.Spider):
    """
    Base spider that all source-specific spiders inherit from.
    Subclasses implement:
      - start_requests_for_area(area: AreaConfig) -> Iterator[scrapy.Request]
      - parse_listing(response) -> PropertyItem
    """

    source: str = ""           # must be set by subclass  e.g. "magicbricks"
    transaction_types: List[str] = ["rent", "sale"]

    custom_settings = {
        "DOWNLOAD_DELAY": config.CRAWL_DELAY_SECONDS,
        "CONCURRENT_REQUESTS_PER_DOMAIN": config.CRAWL_CONCURRENT_REQUESTS_PER_DOMAIN,
        "ROBOTSTXT_OBEY": True,
        "COOKIES_ENABLED": True,
        "RETRY_TIMES": config.CRAWL_MAX_RETRIES,
        "RETRY_HTTP_CODES": [429, 500, 502, 503, 504],
        "DOWNLOADER_MIDDLEWARES": {
            "scrapy.downloadermiddlewares.retry.RetryMiddleware": 90,
            "scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware": 110,
        },
        "DEFAULT_REQUEST_HEADERS": {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-IN,en;q=0.9",
        },
    }

    def start_requests(self) -> Iterator[scrapy.Request]:
        """Iterate over all configured areas × transaction types."""
        tx_types = (
            self.transaction_types
            if config.TRANSACTION_TYPE == "both"
            else [config.TRANSACTION_TYPE]
        )
        for area_key in TARGET_AREAS:
            area = TARGET_AREAS[area_key]
            for tx_type in tx_types:
                log.info("[%s] Starting crawl → %s / %s", self.source, area.name, tx_type)
                yield from self.start_requests_for_area(area, tx_type)

    @abstractmethod
    def start_requests_for_area(
        self, area: AreaConfig, tx_type: str
    ) -> Iterator[scrapy.Request]:
        """Generate seed requests for the given area + transaction type."""
        ...

    @abstractmethod
    def parse_listing(self, response: scrapy.http.Response) -> Optional[PropertyItem]:
        """Extract a PropertyItem from a listing detail page."""
        ...

    # ── Shared Utilities ──────────────────────────────────────────────────────

    @staticmethod
    def make_doc_id(source: str, source_id: str) -> str:
        """Deterministic ES document ID → enables idempotent upserts."""
        raw = f"{source}::{source_id}"
        return hashlib.sha256(raw.encode()).hexdigest()

    from crawler.utils.parsers import parse_price as utils_parse_price, parse_area_sqft as utils_parse_sqft, clean_text as utils_clean_text

    @staticmethod
    def parse_price(text: str) -> Optional[float]:
        """Parse Indian price strings into a float (INR)."""
        from crawler.utils.parsers import parse_price as _p
        return _p(text)

    @staticmethod
    def parse_area_sqft(text: str) -> Optional[float]:
        """Extract numeric sq.ft value from strings."""
        from crawler.utils.parsers import parse_area_sqft as _s
        return _s(text)

    @staticmethod
    def clean_text(text: str) -> str:
        """Strip whitespace/newlines from scraped strings."""
        from crawler.utils.parsers import clean_text as _c
        return _c(text)
