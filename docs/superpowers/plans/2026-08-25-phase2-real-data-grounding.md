# Phase 2: Ground the "Truth" in Real Data — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `agents/supervisor.py`'s LLM-guessed lat/lon and `agents/neighbourhood.py`'s LLM-hallucinated "real" schools/hospitals/metro/markets with real lookups against OpenStreetMap's free Nominatim (geocoding) and Overpass (facility search) APIs, computing distance locally via haversine.

**Architecture:** Two new thin client modules (`agents/geocoding.py`, `agents/facilities.py`) wrap the two OSM APIs with `requests` + `tenacity` retry, mirroring `agents/llm_call.py`'s retry shape. `supervisor_node`'s LLM role shrinks to extracting `locality`/`structured_address` from listing text (a new, trimmed prompt/schema); geocoding itself moves to `geocode_address()`. `neighbourhood_node` drops its LLM call entirely — `cached_locality_lookup`'s compute function now calls `find_nearby_facilities()` instead. Both nodes keep their existing `AgentState` input/output shape, their existing fallback functions (`fallback_address_resolution`, `fallback_neighbourhood_analysis`, unchanged from Phase 1), and the existing `used_fallback` field semantics.

**Tech Stack:** `requests==2.31.0` (already pinned), `tenacity==8.3.0` (already pinned), `responses==0.25.3` (already pinned, currently only used by crawler tests — reused here to mock Nominatim/Overpass HTTP calls) — no new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-25-phase2-real-data-grounding-design.md`

## Global Constraints

- Do not touch `tests/test_items.py` — pre-existing broken import, Phase 0, still out of scope.
- Do not change `AgentState`'s keys or any node function's signature `def node(state: AgentState) -> dict`.
- New code must be testable without live network access — every HTTP call in tests is mocked via `responses`, never hits real Nominatim/Overpass.
- `GeocodingError` for "no match found" must NOT be retried (it's a deterministic result, retrying wastes time/backoff for no benefit) — only `requests.RequestException` (network/HTTP failures) triggers `tenacity` retry. `FacilityLookupError`'s retry scope is the request itself; an empty result set from Overpass is not an error.
- Config additions (`NOMINATIM_BASE_URL`, `OVERPASS_BASE_URL`, `OSM_USER_AGENT`, `OSM_REQUEST_TIMEOUT_SECONDS`) must have working public defaults — no `.env` changes required to run, unlike the LLM provider settings.
- Nominatim's usage policy requires an identifying `User-Agent` header on every request — never omit it.

---

### Task 1: OSM config + real geocoding client

**Files:**
- Modify: `config/settings.py` (add 4 fields)
- Create: `agents/geocoding.py`
- Test: `tests/test_geocoding.py`

**Interfaces:**
- Produces: `geocode_address(query: str, max_attempts: int = 3, wait_min: float = 1.0, wait_max: float = 8.0) -> GeoPoint`, `GeocodingError` — consumed by `agents/supervisor.py` in Task 5.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_geocoding.py
import pytest
import responses

from agents.geocoding import geocode_address, GeocodingError
from config.settings import config


@responses.activate
def test_geocode_address_success():
    responses.add(
        responses.GET,
        f"{config.NOMINATIM_BASE_URL}/search",
        json=[{"lat": "12.9698", "lon": "77.7500", "display_name": "Whitefield, Bangalore"}],
        status=200,
    )

    result = geocode_address("Whitefield, Bangalore, Karnataka")

    assert result.lat == 12.9698
    assert result.lon == 77.7500


@responses.activate
def test_geocode_address_sends_identifying_user_agent():
    responses.add(
        responses.GET,
        f"{config.NOMINATIM_BASE_URL}/search",
        json=[{"lat": "12.9698", "lon": "77.7500"}],
        status=200,
    )

    geocode_address("Whitefield, Bangalore")

    sent_headers = responses.calls[0].request.headers
    assert sent_headers["User-Agent"] == config.OSM_USER_AGENT


@responses.activate
def test_geocode_address_no_match_raises_without_retrying():
    responses.add(
        responses.GET,
        f"{config.NOMINATIM_BASE_URL}/search",
        json=[],
        status=200,
    )

    with pytest.raises(GeocodingError):
        geocode_address("Nonexistent Place, Nowhere", wait_min=0.01, wait_max=0.05)

    assert len(responses.calls) == 1  # no-match is not retried


@responses.activate
def test_geocode_address_retries_then_succeeds_on_transient_network_error():
    responses.add(responses.GET, f"{config.NOMINATIM_BASE_URL}/search", status=503)
    responses.add(responses.GET, f"{config.NOMINATIM_BASE_URL}/search", status=503)
    responses.add(
        responses.GET,
        f"{config.NOMINATIM_BASE_URL}/search",
        json=[{"lat": "12.9698", "lon": "77.7500"}],
        status=200,
    )

    result = geocode_address("Whitefield, Bangalore", wait_min=0.01, wait_max=0.05)

    assert result.lat == 12.9698
    assert len(responses.calls) == 3


@responses.activate
def test_geocode_address_raises_after_max_attempts_on_persistent_network_error():
    responses.add(responses.GET, f"{config.NOMINATIM_BASE_URL}/search", status=503)
    responses.add(responses.GET, f"{config.NOMINATIM_BASE_URL}/search", status=503)

    with pytest.raises(GeocodingError):
        geocode_address("Whitefield, Bangalore", max_attempts=2, wait_min=0.01, wait_max=0.05)

    assert len(responses.calls) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/deepeshmw_google_com/github/Rental-Truth-Teller && source .venv/bin/activate && PYTHONPATH=. python -m pytest tests/test_geocoding.py -v`
Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'agents.geocoding'` (and `config.NOMINATIM_BASE_URL` doesn't exist yet either)

- [ ] **Step 3: Add the 4 config fields**

In `config/settings.py`, add this section after the `USE_MOCK_LLM` field (before `# ── Logging ──...`):

```python
    # ── OpenStreetMap (geocoding + facility lookups) ─────────────────────────────
    NOMINATIM_BASE_URL: str = Field(default="https://nominatim.openstreetmap.org")
    OVERPASS_BASE_URL: str = Field(default="https://overpass-api.de/api/interpreter")
    OSM_USER_AGENT: str = Field(default="RentalTruthTeller/1.0")
    OSM_REQUEST_TIMEOUT_SECONDS: int = Field(default=10)
```

- [ ] **Step 4: Write `agents/geocoding.py`**

```python
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `PYTHONPATH=. python -m pytest tests/test_geocoding.py -v`
Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add config/settings.py agents/geocoding.py tests/test_geocoding.py
git commit -m "feat: add real Nominatim geocoding client, replacing LLM-guessed coordinates"
```

---

### Task 2: Real facility lookup client

**Files:**
- Create: `agents/facilities.py`
- Test: `tests/test_facilities.py`

**Interfaces:**
- Consumes: `GeoPoint`, `NearbyFacility` (from `agents/state.py`, unchanged).
- Produces: `find_nearby_facilities(geo: GeoPoint, max_attempts: int = 3, wait_min: float = 1.0, wait_max: float = 8.0) -> list[NearbyFacility]`, `haversine_km(a: GeoPoint, b: GeoPoint) -> float`, `FacilityLookupError` — consumed by `agents/neighbourhood.py` in Task 6.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_facilities.py
import pytest
import responses

from agents.facilities import find_nearby_facilities, haversine_km, FacilityLookupError
from agents.state import GeoPoint
from config.settings import config

WHITEFIELD = GeoPoint(lat=12.9698, lon=77.7500)


def test_haversine_km_known_distance():
    # 1 degree of longitude at the equator is ~111.19 km (2*pi*R/360, R=6371km)
    a = GeoPoint(lat=0.0, lon=0.0)
    b = GeoPoint(lat=0.0, lon=1.0)
    assert abs(haversine_km(a, b) - 111.19) < 0.1


def test_haversine_km_zero_for_same_point():
    assert haversine_km(WHITEFIELD, WHITEFIELD) == 0.0


@responses.activate
def test_find_nearby_facilities_returns_closest_per_type_sorted_by_distance():
    elements = [
        {"type": "node", "id": 1, "lat": 12.975, "lon": 77.755, "tags": {"amenity": "school", "name": "Far School"}},
        {"type": "node", "id": 2, "lat": 12.970, "lon": 77.751, "tags": {"amenity": "school", "name": "Near School"}},
        {"type": "node", "id": 3, "lat": 12.971, "lon": 77.749, "tags": {"amenity": "hospital", "name": "City Hospital"}},
        {"type": "node", "id": 4, "lat": 12.969, "lon": 77.751, "tags": {"shop": "supermarket", "name": "Big Bazaar"}},
        {"type": "node", "id": 5, "lat": 12.972, "lon": 77.753, "tags": {"railway": "station", "name": "Whitefield Metro"}},
        {"type": "node", "id": 6, "lat": 12.980, "lon": 77.760, "tags": {"amenity": "restaurant", "name": "Not A Facility"}},
    ]
    responses.add(
        responses.POST,
        config.OVERPASS_BASE_URL,
        json={"elements": elements},
        status=200,
    )

    result = find_nearby_facilities(WHITEFIELD)

    school_names = [f.name for f in result if f.facility_type == "school"]
    assert school_names == ["Near School", "Far School"]  # closest first
    assert any(f.name == "City Hospital" and f.facility_type == "hospital" for f in result)
    assert any(f.name == "Big Bazaar" and f.facility_type == "market" for f in result)
    assert any(f.name == "Whitefield Metro" and f.facility_type == "metro" for f in result)
    assert not any(f.name == "Not A Facility" for f in result)  # unmapped tag excluded


@responses.activate
def test_find_nearby_facilities_dedupes_by_element_id():
    elements = [
        {"type": "node", "id": 7, "lat": 12.972, "lon": 77.753, "tags": {"railway": "station", "public_transport": "station", "name": "Whitefield Metro"}},
        {"type": "node", "id": 7, "lat": 12.972, "lon": 77.753, "tags": {"railway": "station", "public_transport": "station", "name": "Whitefield Metro"}},
    ]
    responses.add(
        responses.POST,
        config.OVERPASS_BASE_URL,
        json={"elements": elements},
        status=200,
    )

    result = find_nearby_facilities(WHITEFIELD)

    metro_matches = [f for f in result if f.facility_type == "metro"]
    assert len(metro_matches) == 1


@responses.activate
def test_find_nearby_facilities_skips_unnamed_elements():
    elements = [
        {"type": "node", "id": 8, "lat": 12.970, "lon": 77.751, "tags": {"amenity": "school"}},  # no name
    ]
    responses.add(
        responses.POST,
        config.OVERPASS_BASE_URL,
        json={"elements": elements},
        status=200,
    )

    result = find_nearby_facilities(WHITEFIELD)

    assert result == []


@responses.activate
def test_find_nearby_facilities_empty_result_is_not_an_error():
    responses.add(
        responses.POST,
        config.OVERPASS_BASE_URL,
        json={"elements": []},
        status=200,
    )

    result = find_nearby_facilities(WHITEFIELD)

    assert result == []


@responses.activate
def test_find_nearby_facilities_raises_after_max_attempts_on_persistent_network_error():
    responses.add(responses.POST, config.OVERPASS_BASE_URL, status=503)
    responses.add(responses.POST, config.OVERPASS_BASE_URL, status=503)

    with pytest.raises(FacilityLookupError):
        find_nearby_facilities(WHITEFIELD, max_attempts=2, wait_min=0.01, wait_max=0.05)

    assert len(responses.calls) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. python -m pytest tests/test_facilities.py -v`
Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'agents.facilities'`

- [ ] **Step 3: Write `agents/facilities.py`**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. python -m pytest tests/test_facilities.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add agents/facilities.py tests/test_facilities.py
git commit -m "feat: add real Overpass facility lookup client, replacing LLM-hallucinated landmarks"
```

---

### Task 3: Update `agents/schemas.py` — drop LLM geocode/neighbourhood schemas, add locality extraction schema

**Files:**
- Modify: `agents/schemas.py` (whole file)
- Modify: `tests/test_schemas.py` (whole file)

**Interfaces:**
- Removes: `GeocodeResult`, `FacilityResult`, `NeighbourhoodResult` (no longer produced by any LLM call after Tasks 5-6 land).
- Produces: `LocalityExtractionResult(locality: str, structured_address: str)` — consumed by `agents/supervisor.py` in Task 5.

- [ ] **Step 1: Write the failing test**

Replace `tests/test_schemas.py` in full:

```python
# tests/test_schemas.py
import pytest
from pydantic import ValidationError

from agents.schemas import (
    LocalityExtractionResult,
    FinancialsResult,
    BenchmarksResult,
    VibeResult,
    SynthesisResult,
)


def test_locality_extraction_result_requires_both_fields():
    result = LocalityExtractionResult(
        locality="Whitefield",
        structured_address="Whitefield, Bangalore, Karnataka",
    )
    assert result.locality == "Whitefield"

    with pytest.raises(ValidationError):
        LocalityExtractionResult(locality="Whitefield")


def test_financials_result_defaults():
    result = FinancialsResult()
    assert result.rent == 0.0
    assert result.deposit == 0.0
    assert result.area_sqft is None


def test_benchmarks_result_requires_both_fields():
    result = BenchmarksResult(avg_price_per_sqft=45.0, std_price_per_sqft=6.0)
    assert result.avg_price_per_sqft == 45.0

    with pytest.raises(ValidationError):
        BenchmarksResult(avg_price_per_sqft=45.0)


def test_vibe_result_defaults():
    result = VibeResult()
    assert result.amenity_vs_claim_diffs == []
    assert result.listing_nlp_sentiment == "Neutral"


def test_synthesis_result_requires_core_fields():
    result = SynthesisResult(
        fair_range_min=32000.0,
        fair_range_max=38000.0,
        overpriced_percentage=12.5,
        neighbourhood_score=8.0,
    )
    assert result.red_flags == []
    assert result.broker_questionnaire == []

    with pytest.raises(ValidationError):
        SynthesisResult(fair_range_min=32000.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. python -m pytest tests/test_schemas.py -v`
Expected: FAIL/ERROR — `ImportError: cannot import name 'LocalityExtractionResult' from 'agents.schemas'`

- [ ] **Step 3: Replace `agents/schemas.py` contents**

```python
# agents/schemas.py
"""
agents/schemas.py
──────────────────
Pydantic models describing the exact JSON shape each remaining LLM prompt
in agents/prompts.py must return. Used with PydanticOutputParser (see
agents/llm_call.py) instead of hand-rolled JSON string scraping.

Geocoding and nearby-facility lookups no longer go through the LLM (see
agents/geocoding.py and agents/facilities.py) — LocalityExtractionResult
covers only the text-extraction step that still needs the LLM.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class LocalityExtractionResult(BaseModel):
    locality: str = Field(description="Target locality or area name in Bangalore, e.g. Whitefield, Koramangala")
    structured_address: str = Field(description="Cleaned, structured address string ending in Bangalore, Karnataka, suitable for a geocoding lookup")


class FinancialsResult(BaseModel):
    rent: float = Field(default=0.0, description="Monthly rent in INR, 0 if not found")
    deposit: float = Field(default=0.0, description="Security deposit in INR, 0 if not found")
    area_sqft: Optional[float] = Field(default=None, description="Property area in square feet, null if not found")


class BenchmarksResult(BaseModel):
    avg_price_per_sqft: float = Field(description="Typical average rent rate in INR per sqft for this locality")
    std_price_per_sqft: float = Field(description="Realistic standard deviation in INR per sqft for pricing variance")


class VibeResult(BaseModel):
    amenity_vs_claim_diffs: List[str] = Field(default_factory=list, description="Discrepancies between claims and reality found in the listing")
    community_signals: List[str] = Field(default_factory=list, description="Neighbourhood vibe and safety signals extracted from text")
    diet_pet_lifestyle: List[str] = Field(default_factory=list, description="Restrictive rules like food, pets, gender, marital status constraints")
    listing_nlp_sentiment: str = Field(default="Neutral", description="One word describing overall listing sentiment")


class SynthesisResult(BaseModel):
    fair_range_min: float = Field(description="Minimum of the dynamic fair rent range estimate")
    fair_range_max: float = Field(description="Maximum of the dynamic fair rent range estimate")
    overpriced_percentage: float = Field(description="Percentage the listing is overpriced relative to fair range, negative if underpriced")
    red_flags: List[str] = Field(default_factory=list, description="Extreme prices, strict lease terms, or POI deficiencies found")
    neighbourhood_score: float = Field(description="Score from 0 to 10 based on proximity to metro, schools, hospitals, markets")
    broker_questionnaire: List[str] = Field(default_factory=list, description="4 key clever questions to ask the broker or owner")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. python -m pytest tests/test_schemas.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add agents/schemas.py tests/test_schemas.py
git commit -m "refactor: drop LLM geocode/neighbourhood schemas, add locality extraction schema"
```

---

### Task 4: Update `agents/prompts.py` — drop geocode/neighbourhood prompts, add locality extraction prompt

**Files:**
- Modify: `agents/prompts.py` (whole file)
- Modify: `tests/test_prompts.py` (whole file)

**Interfaces:**
- Removes: `GEOCODE_PROMPT`, `RESOLVE_NEIGHBOURHOOD_PROMPT`.
- Produces: `EXTRACT_LOCALITY_PROMPT` — consumed by `agents/supervisor.py` in Task 5.

- [ ] **Step 1: Write the failing test**

Replace `tests/test_prompts.py` in full:

```python
# tests/test_prompts.py
from agents import prompts

ALL_PROMPTS = [
    prompts.EXTRACT_LOCALITY_PROMPT,
    prompts.EXTRACT_FINANCIALS_PROMPT,
    prompts.ESTIMATE_BENCHMARKS_PROMPT,
    prompts.VIBE_CHECK_PROMPT,
    prompts.SYNTHESIS_PROMPT,
]


def test_prompts_no_longer_hand_roll_json_instructions():
    for prompt in ALL_PROMPTS:
        assert "raw JSON" not in prompt
        assert "```" not in prompt


def test_prompts_still_have_their_input_variables():
    assert "{listing_input}" in prompts.EXTRACT_LOCALITY_PROMPT
    assert "{listing_input}" in prompts.EXTRACT_FINANCIALS_PROMPT
    assert "{locality}" in prompts.ESTIMATE_BENCHMARKS_PROMPT
    assert "{listing_input}" in prompts.VIBE_CHECK_PROMPT
    assert "{address_resolved}" in prompts.SYNTHESIS_PROMPT
    assert "{pricing_data}" in prompts.SYNTHESIS_PROMPT
    assert "{vibe_data}" in prompts.SYNTHESIS_PROMPT
    assert "{neighbourhood_data}" in prompts.SYNTHESIS_PROMPT
    assert "{critique_section}" in prompts.SYNTHESIS_PROMPT


def test_geocode_and_neighbourhood_prompts_removed():
    assert not hasattr(prompts, "GEOCODE_PROMPT")
    assert not hasattr(prompts, "RESOLVE_NEIGHBOURHOOD_PROMPT")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. python -m pytest tests/test_prompts.py -v`
Expected: FAIL — `AttributeError: module 'agents.prompts' has no attribute 'EXTRACT_LOCALITY_PROMPT'`

- [ ] **Step 3: Replace `agents/prompts.py` contents**

```python
# agents/prompts.py
EXTRACT_LOCALITY_PROMPT = """You are a Bangalore spatial resolver agent.
Analyze the given rental property listing content and extract:
1. The target locality or area in Bangalore (e.g. Whitefield, Koramangala, Indiranagar, HSR Layout).
2. A cleaned, structured address ending in Bangalore, Karnataka — suitable for a geocoding lookup.

Raw Listing Content:
{listing_input}
"""

EXTRACT_FINANCIALS_PROMPT = """You are a property financial extractor. Given the raw property description, extract:
1. Monthly Rent in INR.
2. Security Deposit in INR.
3. Property Area in SqFt.

Raw listing content:
{listing_input}
"""

ESTIMATE_BENCHMARKS_PROMPT = """You are a Bangalore real estate pricing intelligence analyst.
Given a locality in Bangalore, estimate realistic market pricing benchmarks:
1. The typical average rent rate in INR per SqFt (e.g. 35.0 to 65.0).
2. A realistic standard deviation in INR per SqFt for pricing variance in this locality (usually between 4.0 and 10.0).

Locality: {locality}
"""

VIBE_CHECK_PROMPT = """You are the "Vibe Check Agent" in a rental verification network.
Given the user's raw property description or input listing, analyze the text to find:
1. Potential discrepancy red flags (e.g., listing claiming "next to metro" but mentioning "20 minutes walk").
2. Community signals (e.g., family-focused, nightlife, noise problems, security).
3. Lifestyle/diet/pet rules (e.g., "Only pure veg", "No pets", "Tenant type: bachelor boys only").
4. Overall sentiment profile of the listing (e.g. Enthusiastic, Pressuring, Deceptive, Warm).

Raw Listing Input:
{listing_input}
"""

SYNTHESIS_PROMPT = """You are the "Synthesis Agent" in a rental validation multi-agent network.
Collect all preceding sub-agent analyses and synthesize them into a consolidated "Verdict Card" report.

Context data:
- Address Resolved: {address_resolved}
- Price Analysis: {pricing_data}
- Vibe & Rules: {vibe_data}
- Neighborhood & Metro proximity: {neighbourhood_data}

{critique_section}

Output parameters required:
1. Overpriced Percentage: directly mapped or adjusted from Price Analysis.
2. Red Flags list: Gather extreme prices, strict lease terms (e.g. high deposit, bachelors penalty, veg-only restrictions) or POI deficiencies (e.g. no metro within 3km).
3. Broker Questionnaire: 4 key critical/clever questions to ask the broker or owner based on discrepancies OR constraints identified here.
4. Fair Range: Return a dynamic estimate minimum and maximum rate (e.g., average rent +/- 10%).
5. Neighbourhood Score: Compute a score from 0 to 10 based on POIs (Metro < 1.5km adds 4 pts, School > 0 adds 2 pts, Hospital > 0 adds 2 pts, Market > 0 adds 2 pts).
"""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. python -m pytest tests/test_prompts.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add agents/prompts.py tests/test_prompts.py
git commit -m "refactor: drop geocode/neighbourhood prompts, add locality extraction prompt"
```

---

### Task 5: Rewire `agents/supervisor.py` onto real geocoding

**Files:**
- Modify: `agents/supervisor.py` (whole file)
- Modify: `tests/test_supervisor.py` (whole file)

**Interfaces:**
- Consumes: `LocalityExtractionResult` (Task 3), `EXTRACT_LOCALITY_PROMPT` (Task 4), `geocode_address`, `GeocodingError` (Task 1).
- Produces: unchanged — `supervisor_node(state: AgentState) -> dict` with keys `address_resolved`, `messages`.

- [ ] **Step 1: Write the failing test**

Replace `tests/test_supervisor.py` in full:

```python
# tests/test_supervisor.py
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

import agents.supervisor as supervisor_mod
from agents.state import AgentState, GeoPoint
from agents.geocoding import GeocodingError


def _base_state(listing_input: str) -> AgentState:
    return {
        "listing_input": listing_input,
        "address_resolved": None,
        "pricing_data": None,
        "vibe_data": None,
        "neighbourhood_data": None,
        "final_verdict": None,
        "messages": [],
    }


def test_supervisor_uses_static_dictionary_when_locality_recognized():
    state = _base_state("2BHK for rent in Whitefield, Bangalore")
    result = supervisor_mod.supervisor_node(state)

    assert result["address_resolved"].locality == "Whitefield"
    assert result["address_resolved"].used_fallback is False
    assert result["address_resolved"].confidence == 0.9


def test_supervisor_falls_through_to_real_geocoding_for_unknown_locality(monkeypatch):
    fake_llm = RunnableLambda(
        lambda _: AIMessage(
            content='{"locality": "JP Nagar", "structured_address": "JP Nagar, Bangalore, Karnataka"}'
        )
    )
    monkeypatch.setattr(supervisor_mod, "get_llm", lambda temperature=0.1: fake_llm)
    monkeypatch.setattr(
        supervisor_mod, "geocode_address", lambda query: GeoPoint(lat=12.9077, lon=77.5928)
    )

    state = _base_state("2BHK for rent in JP Nagar")
    result = supervisor_mod.supervisor_node(state)

    assert result["address_resolved"].locality == "JP Nagar"
    assert result["address_resolved"].geo.lat == 12.9077
    assert result["address_resolved"].used_fallback is False


def test_supervisor_uses_fallback_when_llm_call_fails(monkeypatch):
    fake_llm = RunnableLambda(lambda _: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(supervisor_mod, "get_llm", lambda temperature=0.1: fake_llm)

    state = _base_state("2BHK for rent in JP Nagar")
    result = supervisor_mod.supervisor_node(state)

    assert result["address_resolved"].used_fallback is True
    assert result["address_resolved"].locality == "Whitefield"


def test_supervisor_uses_fallback_when_geocoding_fails(monkeypatch):
    fake_llm = RunnableLambda(
        lambda _: AIMessage(
            content='{"locality": "JP Nagar", "structured_address": "JP Nagar, Bangalore, Karnataka"}'
        )
    )
    monkeypatch.setattr(supervisor_mod, "get_llm", lambda temperature=0.1: fake_llm)

    def _raise_geocoding_error(query):
        raise GeocodingError(f"No match for {query!r}")

    monkeypatch.setattr(supervisor_mod, "geocode_address", _raise_geocoding_error)

    state = _base_state("2BHK for rent in JP Nagar")
    result = supervisor_mod.supervisor_node(state)

    assert result["address_resolved"].used_fallback is True
    assert result["address_resolved"].locality == "Whitefield"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. python -m pytest tests/test_supervisor.py -v`
Expected: FAIL — old code has no `geocode_address` attribute to monkeypatch, and imports `GeocodeResult`/`GEOCODE_PROMPT` which no longer exist after Tasks 3-4

- [ ] **Step 3: Replace `agents/supervisor.py` contents**

```python
# agents/supervisor.py
"""
agents/supervisor.py
────────────────────
Supervisor Agent: First entrypoint. Extracts locality/address from raw
listing text via LLM, then resolves real coordinates via Nominatim.
"""

from __future__ import annotations

import logging
from agents.config import get_llm
from agents.prompts import EXTRACT_LOCALITY_PROMPT
from agents.state import AgentState, AddressResolved, GeoPoint
from agents.fallbacks import fallback_address_resolution
from agents.llm_call import call_llm_structured, LLMCallError
from agents.schemas import LocalityExtractionResult
from agents.geocoding import geocode_address, GeocodingError

log = logging.getLogger(__name__)

def supervisor_node(state: AgentState) -> dict:
    log.info("[Supervisor Agent] Resolving address & geocoding listing…")

    listing_input = state.get("listing_input", "")
    if not listing_input:
        # Defaults fallback
        res = AddressResolved(
            raw_address="Bangalore",
            structured_address="Bangalore, Karnataka, IndiaIndex",
            locality="Bangalore",
            geo=GeoPoint(lat=12.9716, lon=77.5946),
            confidence=0.1
        )
        return {"address_resolved": res, "messages": ["[Supervisor Agent] No input listing provided; resolved global default."]}

    # Look up known target areas (from config.areas) before falling back to real geocoding
    from config.areas import TARGET_AREAS
    text_lower = listing_input.lower()
    for key, area_cfg in TARGET_AREAS.items():
        if key in text_lower or area_cfg.name.lower() in text_lower:
            resolved = AddressResolved(
                raw_address=listing_input[:100],
                structured_address=f"{area_cfg.name}, Bangalore, Karnataka, India",
                locality=area_cfg.name,
                geo=GeoPoint(lat=area_cfg.latitude, lon=area_cfg.longitude),
                confidence=0.9
            )
            msg = f"[Supervisor Agent] Geolocated to `{resolved.locality}` via static dictionary. Coords: ({resolved.geo.lat}, {resolved.geo.lon})."
            log.info(msg)
            return {
                "address_resolved": resolved,
                "messages": [msg]
            }

    llm = get_llm(temperature=0.1)

    try:
        extraction = call_llm_structured(llm, EXTRACT_LOCALITY_PROMPT, {"listing_input": listing_input}, LocalityExtractionResult)
        geo = geocode_address(extraction.structured_address or extraction.locality)

        resolved = AddressResolved(
            raw_address=listing_input[:100],
            structured_address=extraction.structured_address,
            locality=extraction.locality,
            geo=geo,
            confidence=0.9
        )

        msg = f"[Supervisor Agent] Geolocated to `{resolved.locality}` via OSM. Coords: ({resolved.geo.lat}, {resolved.geo.lon})."
        log.info(msg)
        return {
            "address_resolved": resolved,
            "messages": [msg]
        }
    except (LLMCallError, GeocodingError) as e:
        log.error(f"[Supervisor Agent] Address resolution failed: {e}")
        return fallback_address_resolution(listing_input, str(e))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. python -m pytest tests/test_supervisor.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add agents/supervisor.py tests/test_supervisor.py
git commit -m "refactor: resolve real coordinates via Nominatim in supervisor agent"
```

---

### Task 6: Rewire `agents/neighbourhood.py` onto real facility lookups

**Files:**
- Modify: `agents/neighbourhood.py` (whole file)
- Modify: `tests/test_neighbourhood.py` (whole file)

**Interfaces:**
- Consumes: `find_nearby_facilities`, `FacilityLookupError` (Task 2); `cached_locality_lookup` (Phase 1, unchanged).
- Produces: unchanged — `neighbourhood_node(state: AgentState) -> dict` with keys `neighbourhood_data`, `messages`.

- [ ] **Step 1: Write the failing test**

Replace `tests/test_neighbourhood.py` in full:

```python
# tests/test_neighbourhood.py
import agents.neighbourhood as neigh_mod
from agents.cache import clear_locality_cache
from agents.state import AgentState, AddressResolved, GeoPoint, NearbyFacility
from agents.facilities import FacilityLookupError


def _state(locality: str) -> AgentState:
    return {
        "listing_input": "listing",
        "address_resolved": AddressResolved(
            raw_address="x", locality=locality, structured_address=f"{locality}, Bangalore",
            geo=GeoPoint(lat=12.97, lon=77.75)
        ),
        "pricing_data": None,
        "vibe_data": None,
        "neighbourhood_data": None,
        "final_verdict": None,
        "messages": [],
    }


def test_neighbourhood_resolves_and_caches_by_locality(monkeypatch):
    clear_locality_cache()
    calls = {"n": 0}

    def fake_find_nearby_facilities(geo):
        calls["n"] += 1
        return [
            NearbyFacility(name="Whitefield Metro", facility_type="metro", distance_km=1.1),
            NearbyFacility(name="Test School", facility_type="school", distance_km=0.9),
        ]

    monkeypatch.setattr(neigh_mod, "find_nearby_facilities", fake_find_nearby_facilities)

    result1 = neigh_mod.neighbourhood_node(_state("Whitefield"))
    result2 = neigh_mod.neighbourhood_node(_state("Whitefield"))

    assert result1["neighbourhood_data"].metro_station == "Whitefield Metro"
    assert result1["neighbourhood_data"].metro_distance_km == 1.1
    assert result1["neighbourhood_data"].school_count == 1
    assert result1["neighbourhood_data"].used_fallback is False
    assert calls["n"] == 1  # second call hit the cache
    assert result2["neighbourhood_data"].metro_station == "Whitefield Metro"


def test_neighbourhood_uses_fallback_on_lookup_failure(monkeypatch):
    clear_locality_cache()

    def fake_find_nearby_facilities(geo):
        raise FacilityLookupError("overpass down")

    monkeypatch.setattr(neigh_mod, "find_nearby_facilities", fake_find_nearby_facilities)

    result = neigh_mod.neighbourhood_node(_state("Jayanagar"))

    assert result["neighbourhood_data"].used_fallback is True
    assert result["neighbourhood_data"].school_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. python -m pytest tests/test_neighbourhood.py -v`
Expected: FAIL — old code has no `find_nearby_facilities` attribute to monkeypatch, and imports `NeighbourhoodResult`/`RESOLVE_NEIGHBOURHOOD_PROMPT` which no longer exist after Tasks 3-4

- [ ] **Step 3: Replace `agents/neighbourhood.py` contents**

```python
# agents/neighbourhood.py
"""
agents/neighbourhood.py
───────────────────────
Neighbourhood Agent: Finds real nearby schools, hospitals, markets, and
metro stations via OpenStreetMap Overpass, and generates a Kibana map pin.
"""

from __future__ import annotations

import logging
from agents.state import AgentState, GeoPoint, NeighbourhoodAnalysis
from agents.fallbacks import fallback_neighbourhood_analysis
from agents.facilities import find_nearby_facilities, FacilityLookupError
from agents.cache import cached_locality_lookup

log = logging.getLogger(__name__)

def neighbourhood_node(state: AgentState) -> dict:
    log.info("[Neighbourhood Agent] Analyzing neighborhood points of interest (POI)…")

    address_resolved = state.get("address_resolved")
    locality = address_resolved.locality if address_resolved else "Bangalore"

    metro_station = f"{locality} Metro Station"
    base_metro_dist = -1.0
    used_fallback = False

    geo = address_resolved.geo if (address_resolved and address_resolved.geo) else GeoPoint(lat=12.9716, lon=77.5946)

    try:
        facilities = cached_locality_lookup(
            f"neighbourhood:{locality}",
            lambda: find_nearby_facilities(geo),
        )

        metro_facility = next((f for f in facilities if f.facility_type == "metro"), None)
        if metro_facility:
            metro_station = metro_facility.name
            base_metro_dist = metro_facility.distance_km

        log.info(f"[Neighbourhood Agent] Resolved closest transit: {metro_station} ({base_metro_dist} km). Total POIs catalogued: {len(facilities)}")

    except FacilityLookupError as exc:
        log.error(f"[Neighbourhood Agent] Error during POI lookup: {exc}. Using robust fallback estimates.")
        base_metro_dist, facilities = fallback_neighbourhood_analysis(locality, metro_station)
        used_fallback = True

    # Summarize metrics for State
    schools_count = sum(1 for f in facilities if f.facility_type == "school")
    hospitals_count = sum(1 for f in facilities if f.facility_type == "hospital")
    markets_count = sum(1 for f in facilities if f.facility_type == "market")

    lat = geo.lat
    lon = geo.lon

    # Formulate a synthetic Kibana map visualize link with coordinates pinned
    kibana_maps_pin = f"http://localhost:5601/app/maps#/map?_g=(filters:!(),refreshInterval:(pause:!t,value:0),time:(from:now-15m,to:now))&_a=(description:'',views:(map:(center:!({lat},{lon}),zoom:15)))"

    analysis_res = NeighbourhoodAnalysis(
        facilities=facilities,
        metro_station=metro_station,
        metro_distance_km=base_metro_dist,
        school_count=schools_count,
        hospital_count=hospitals_count,
        market_count=markets_count,
        kibana_maps_pin_url=kibana_maps_pin,
        used_fallback=used_fallback
    )

    msg = f"[Neighbourhood Agent] POI lookup completed. Metro: {metro_station} ({base_metro_dist}km)."
    log.info(msg)

    return {
        "neighbourhood_data": analysis_res,
        "messages": [msg]
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. python -m pytest tests/test_neighbourhood.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add agents/neighbourhood.py tests/test_neighbourhood.py
git commit -m "refactor: resolve real nearby facilities via Overpass in neighbourhood agent"
```

---

### Task 7: Full regression pass

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run:
```bash
cd /home/deepeshmw_google_com/github/Rental-Truth-Teller
source .venv/bin/activate
PYTHONPATH=. python -m pytest tests/ --ignore=tests/test_items.py -v
```

Expected: all tests pass (Phase 1's 34 plus this plan's ~18 new = ~52 total). `tests/test_items.py` remains excluded (pre-existing, Phase 0, out of scope).

- [ ] **Step 2: Confirm no dead LLM-geocoding/neighbourhood code remains**

Run: `grep -rn "GEOCODE_PROMPT\|RESOLVE_NEIGHBOURHOOD_PROMPT\|GeocodeResult\|NeighbourhoodResult\|FacilityResult" agents/ tests/`

Expected: no matches anywhere (all four were fully replaced in Tasks 3-4, and no node/test still references the old names).

- [ ] **Step 3: Commit the verification (no-op if nothing changed)**

If Steps 1-2 both come back clean, there is nothing to commit — this task is a verification gate. If anything fails, stop and fix the root cause in the relevant earlier task before proceeding.

---

## Out of Scope (deliberately deferred)

- Nominatim's documented ~1 req/sec rate-limit policy: no rate limiter implemented — real traffic to it is rare given `TARGET_AREAS` and Phase 1's locality cache already absorb most requests. Revisit if usage data says otherwise.
- Retrying `geocode_address` with a narrower query (e.g. just `locality`) if the full `structured_address` yields no match — single-query, no cascading fallback strategy; `fallback_address_resolution` is the safety net.
- UI confidence badge surfacing `AddressResolved.confidence`/`used_fallback` — Phase 4 (`plan.md`).
- `tests/test_items.py`'s broken `crawler.spiders.base_spider` import — Phase 0, still out of scope.
