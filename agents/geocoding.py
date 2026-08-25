# agents/geocoding.py
"""
agents/geocoding.py
────────────────────
Real geocoding via OpenStreetMap Nominatim, replacing LLM-guessed coordinates.
"""

from __future__ import annotations

import logging

import requests
from tenacity import Retrying, stop_after_attempt, wait_exponential, retry_if_exception_type

from agents.state import GeoPoint
from config.settings import config as global_config

log = logging.getLogger(__name__)


class GeocodingError(Exception):
    """Raised when geocoding returns no match, or fails after all retry attempts."""


def geocode_address(
    query: str,
    max_attempts: int = 3,
    wait_min: float = 1.0,
    wait_max: float = 8.0,
) -> GeoPoint:
    """Resolves a free-text address/locality string to coordinates via
    Nominatim. Raises GeocodingError immediately on no match (not retried
    — a deterministic result), or after all retries on network/HTTP failure."""

    def _call() -> GeoPoint:
        response = requests.get(
            f"{global_config.NOMINATIM_BASE_URL}/search",
            params={"q": query, "format": "jsonv2", "limit": 1},
            headers={"User-Agent": global_config.OSM_USER_AGENT},
            timeout=global_config.OSM_REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        results = response.json()
        if not results:
            raise GeocodingError(f"No geocoding match for query: {query!r}")
        return GeoPoint(lat=float(results[0]["lat"]), lon=float(results[0]["lon"]))

    retryer = Retrying(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=wait_min, min=wait_min, max=wait_max),
        retry=retry_if_exception_type(requests.RequestException),
        reraise=True,
    )
    try:
        return retryer(_call)
    except requests.RequestException as e:
        log.error(f"[geocode_address] Failed after {max_attempts} attempts: {e}")
        raise GeocodingError(str(e)) from e
