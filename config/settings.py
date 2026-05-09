"""
config/settings.py
──────────────────
Central configuration for the RentalTruth Tier-0 crawler.
All values are driven by environment variables (see .env.example).
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import List

from dotenv import load_dotenv

load_dotenv()


class AppConfig:
    """Singleton-style config loaded from environment variables."""

    # ── Elasticsearch ────────────────────────────────────────────
    ES_HOST: str = os.getenv("ES_HOST", "localhost")
    ES_PORT: int = int(os.getenv("ES_PORT", "9200"))
    ES_SCHEME: str = os.getenv("ES_SCHEME", "http")
    ES_USERNAME: str = os.getenv("ES_USERNAME", "elastic")
    ES_PASSWORD: str = os.getenv("ES_PASSWORD", "changeme")
    ES_INDEX_PROPERTIES: str = os.getenv("ES_INDEX_PROPERTIES", "bangalore_properties")
    ES_INDEX_REPLICA: int = int(os.getenv("ES_INDEX_REPLICA", "0"))
    ES_INDEX_SHARDS: int = int(os.getenv("ES_INDEX_SHARDS", "1"))

    # ── Crawler ──────────────────────────────────────────────────
    CRAWL_DELAY_SECONDS: float = float(os.getenv("CRAWL_DELAY_SECONDS", "2"))
    CRAWL_CONCURRENT_REQUESTS: int = int(os.getenv("CRAWL_CONCURRENT_REQUESTS", "8"))
    CRAWL_CONCURRENT_REQUESTS_PER_DOMAIN: int = int(
        os.getenv("CRAWL_CONCURRENT_REQUESTS_PER_DOMAIN", "2")
    )
    CRAWL_DOWNLOAD_TIMEOUT: int = int(os.getenv("CRAWL_DOWNLOAD_TIMEOUT", "30"))
    CRAWL_MAX_RETRIES: int = int(os.getenv("CRAWL_MAX_RETRIES", "3"))

    # ── Target Config ────────────────────────────────────────────
    BANGALORE_AREAS: List[str] = [
        area.strip()
        for area in os.getenv("BANGALORE_AREAS", "Whitefield,Koramangala").split(",")
        if area.strip()
    ]
    TRANSACTION_TYPE: str = os.getenv("TRANSACTION_TYPE", "both")  # rent | sale | both

    # ── ELSER (Elastic Learned Sparse EncodeR) ───────────────────
    # Uses the built-in .elser-2-elasticsearch endpoint (ES 8.13+).
    # Override ELSER_INFERENCE_ID to use a custom deployed endpoint.
    ELSER_INFERENCE_ID: str = os.getenv("ELSER_INFERENCE_ID", ".elser-2-elasticsearch")
    ELSER_NUM_ALLOCATIONS: int = int(os.getenv("ELSER_NUM_ALLOCATIONS", "1"))
    ELSER_NUM_THREADS: int = int(os.getenv("ELSER_NUM_THREADS", "1"))

    # ── Logging ──────────────────────────────────────────────────
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT: str = os.getenv("LOG_FORMAT", "json")

    @property
    def es_url(self) -> str:
        return f"{self.ES_SCHEME}://{self.ES_HOST}:{self.ES_PORT}"

    @property
    def es_auth(self) -> tuple[str, str]:
        return (self.ES_USERNAME, self.ES_PASSWORD)


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    return AppConfig()


config = get_config()
