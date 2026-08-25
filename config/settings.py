"""
config/settings.py
──────────────────
Central configuration for the RentalTruth system.
Uses pydantic-settings for robust environment variable management.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import List, Optional, Any

from pydantic import Field, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseSettings):
    """Configuration loaded from environment variables."""
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── Elasticsearch connection ──────────────────────────────────────────────
    ES_HOST: str = Field(default="localhost")
    ES_PORT: int = Field(default=9200)
    ES_SCHEME: str = Field(default="http")

    # ── Authentication ────────────────────────────────────────────────────────
    ES_API_KEY: Optional[str] = Field(default=None)
    ES_USERNAME: str = Field(default="elastic")
    ES_PASSWORD: str = Field(default="changeme")

    # ── Index ─────────────────────────────────────────────────────────────────
    ES_INDEX_PROPERTIES: str = Field(default="bangalore_properties")
    ES_INDEX_REPLICA: int = Field(default=0)
    ES_INDEX_SHARDS: int = Field(default=1)

    # ── ELSER ─────────────────────────────────────────────────────────────────
    ELSER_INFERENCE_ID: str = Field(default=".elser-2-elasticsearch")
    ELSER_NUM_ALLOCATIONS: int = Field(default=1)
    ELSER_NUM_THREADS: int = Field(default=1)

    # ── Crawler ───────────────────────────────────────────────────────────────
    CRAWL_DELAY_SECONDS: float = Field(default=2.0)
    CRAWL_CONCURRENT_REQUESTS: int = Field(default=8)
    CRAWL_CONCURRENT_REQUESTS_PER_DOMAIN: int = Field(default=2)
    CRAWL_DOWNLOAD_TIMEOUT: int = Field(default=30)
    CRAWL_MAX_RETRIES: int = Field(default=3)

    # ── Target config ─────────────────────────────────────────────────────────
    # We use Any to bypass pydantic-settings automatic JSON parsing for Lists in .env
    BANGALORE_AREAS: Any = Field(default=["Whitefield", "Koramangala"])
    TRANSACTION_TYPE: str = Field(default="both")   # rent | sale | both

    @field_validator("BANGALORE_AREAS", mode="before")
    @classmethod
    def assemble_areas(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            return [i.strip() for i in v.split(",") if i.strip()]
        return v

    # ── LLM Settings ──────────────────────────────────────────────────────────
    LLM_PROVIDER: str = Field(default="gemini")
    GEMINI_API_KEY: Optional[str] = Field(default=None)
    GEMINI_MODEL: str = Field(default="gemini-flash-latest")

    AWS_ACCESS_KEY_ID: Optional[str] = Field(default=None)
    AWS_SECRET_ACCESS_KEY: Optional[str] = Field(default=None)
    AWS_DEFAULT_REGION: str = Field(default="us-east-1")

    USE_MOCK_LLM: bool = Field(default=False)

    # ── OpenStreetMap (geocoding + facility lookups) ─────────────────────────────
    NOMINATIM_BASE_URL: str = Field(default="https://nominatim.openstreetmap.org")
    OVERPASS_BASE_URL: str = Field(default="https://overpass-api.de/api/interpreter")
    OSM_USER_AGENT: str = Field(default="RentalTruthTeller/1.0")
    # Must stay comfortably above the Overpass query template's own
    # [timeout:25] (see agents/facilities.py) -- otherwise the HTTP client
    # gives up before the server does, turning every slow-but-legitimate
    # query into a client-side timeout + wasted retry.
    OSM_REQUEST_TIMEOUT_SECONDS: int = Field(default=30)

    # ── Logging ───────────────────────────────────────────────────────────────
    LOG_LEVEL: str = Field(default="INFO")
    LOG_FORMAT: str = Field(default="standard")  # standard | json
    CLI_LOG_PATH: str = Field(default="cli.log")
    UI_LOG_PATH: str = Field(default="ui.log")
    BACKEND_LOG_PATH: str = Field(default="backend.log")

    # ── Derived helpers ───────────────────────────────────────────────────────
    @computed_field
    @property
    def es_url(self) -> str:
        return f"{self.ES_SCHEME}://{self.ES_HOST}:{self.ES_PORT}"

    @property
    def uses_api_key(self) -> bool:
        return bool(self.ES_API_KEY)

    @property
    def es_auth(self) -> tuple[str, str]:
        """Basic auth tuple — only used when API key is absent."""
        return (self.ES_USERNAME, self.ES_PASSWORD)


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    return AppConfig()


config = get_config()
