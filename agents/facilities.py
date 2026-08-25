# agents/facilities.py
"""
agents/facilities.py
──────────────────────
Real nearby-facility lookups via OpenStreetMap Overpass, replacing
LLM-hallucinated "real" schools/hospitals/metro/markets.
"""

from __future__ import annotations

import logging
import math
from typing import Optional

import requests
from tenacity import Retrying, stop_after_attempt, wait_exponential

from agents.state import GeoPoint, NearbyFacility
from config.settings import config as global_config

log = logging.getLogger(__name__)

EARTH_RADIUS_KM = 6371.0

OVERPASS_QUERY_TEMPLATE = """
[out:json][timeout:25];
(
  node["amenity"="school"](around:3000,{lat},{lon});
  node["amenity"="hospital"](around:3000,{lat},{lon});
  node["amenity"="clinic"](around:3000,{lat},{lon});
  node["shop"="supermarket"](around:2000,{lat},{lon});
  node["railway"="station"](around:5000,{lat},{lon});
  node["public_transport"="station"](around:5000,{lat},{lon});
);
out center;
"""

_TAG_TO_FACILITY_TYPE = {
    ("amenity", "school"): "school",
    ("amenity", "hospital"): "hospital",
    ("amenity", "clinic"): "hospital",
    ("shop", "supermarket"): "market",
    ("railway", "station"): "metro",
    ("public_transport", "station"): "metro",
}

_TYPE_LIMITS = (("metro", 1), ("school", 2), ("hospital", 2), ("market", 2))


class FacilityLookupError(Exception):
    """Raised when the Overpass query fails after all retry attempts."""


def haversine_km(a: GeoPoint, b: GeoPoint) -> float:
    """Great-circle distance between two points in kilometers."""
    lat1, lon1 = math.radians(a.lat), math.radians(a.lon)
    lat2, lon2 = math.radians(b.lat), math.radians(b.lon)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def _facility_type_for_tags(tags: dict) -> Optional[str]:
    for (key, value), facility_type in _TAG_TO_FACILITY_TYPE.items():
        if tags.get(key) == value:
            return facility_type
    return None


def find_nearby_facilities(
    geo: GeoPoint,
    max_attempts: int = 3,
    wait_min: float = 1.0,
    wait_max: float = 8.0,
) -> list[NearbyFacility]:
    """Queries Overpass for schools, hospitals, markets, and metro/transit
    stations near geo, computes haversine distance to each, and returns
    the closest matches per type (2 schools, 2 hospitals, 2 markets, 1
    metro), sorted nearest-first. An empty result from Overpass is not an
    error. Raises FacilityLookupError after all retries on network/HTTP
    failure."""
    query = OVERPASS_QUERY_TEMPLATE.format(lat=geo.lat, lon=geo.lon)

    def _call() -> list[dict]:
        response = requests.post(
            global_config.OVERPASS_BASE_URL,
            data={"data": query},
            headers={"User-Agent": global_config.OSM_USER_AGENT},
            timeout=global_config.OSM_REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json().get("elements", [])

    retryer = Retrying(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=wait_min, min=wait_min, max=wait_max),
        reraise=True,
    )
    try:
        elements = retryer(_call)
    except Exception as e:
        log.error(f"[find_nearby_facilities] Failed after {max_attempts} attempts: {e}")
        raise FacilityLookupError(str(e)) from e

    seen_ids = set()
    candidates: list[NearbyFacility] = []
    for el in elements:
        el_id = el.get("id")
        if el_id in seen_ids:
            continue
        tags = el.get("tags", {})
        name = tags.get("name")
        if not name:
            continue
        facility_type = _facility_type_for_tags(tags)
        if facility_type is None:
            continue
        seen_ids.add(el_id)
        point = GeoPoint(lat=el["lat"], lon=el["lon"])
        candidates.append(NearbyFacility(
            name=name,
            facility_type=facility_type,
            distance_km=round(haversine_km(geo, point), 2),
        ))

    result: list[NearbyFacility] = []
    for f_type, limit in _TYPE_LIMITS:
        matches = sorted((c for c in candidates if c.facility_type == f_type), key=lambda c: c.distance_km)
        result.extend(matches[:limit])

    log.info(f"[find_nearby_facilities] Found {len(result)} facilities near ({geo.lat}, {geo.lon}).")
    return result
