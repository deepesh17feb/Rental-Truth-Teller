# Phase 2: Ground the "Truth" in Real Data — Design

**Status:** Approved by user 2026-08-25, pending spec self-review.

## Problem

An app called "Truth-Teller" currently asks a raw LLM to invent geocoordinates (`GEOCODE_PROMPT`) and "real" nearby schools/hospitals/metro stations (`RESOLVE_NEIGHBOURHOOD_PROMPT`, which literally instructs the model to "Resolve real, actual nearby facilities"). The LLM has no way to know what's actually near a given address — it produces plausible-sounding hallucinations. This phase replaces both with real, deterministic lookups against OpenStreetMap.

## Decisions

- **Provider: OpenStreetMap** — Nominatim for geocoding, Overpass for facility search. Free, no API key, no billing. Matches this project's existing no-paid-geo-API footprint.
- **Distance: haversine straight-line**, computed locally, no extra API call or dependency.
- **UI confidence badge: deferred to Phase 4.** This phase is backend-only — real data flows through the existing `confidence`/`used_fallback` fields, but nothing new is added to `rendering/ui/app.py` or the CLI to surface it.
- **LLM's remaining role:** financial extraction, vibe analysis, synthesis narrative stay LLM-driven (free-text understanding, not fact lookup — Phase 1's structured-output/retry work already covers these, no changes needed).

## Architecture

Two new client modules, each a thin wrapper around one public OSM API, using `requests` (already pinned) with `tenacity` retry (already pinned) — no new dependencies.

### `agents/geocoding.py`

```python
class GeocodingError(Exception):
    """Raised when geocoding fails after all retries, or the API returns no match."""

def geocode_address(query: str) -> GeoPoint:
    """Resolves a free-text address/locality string to coordinates via
    Nominatim. Raises GeocodingError on failure or no match."""
```

Calls `GET {NOMINATIM_BASE_URL}/search` with `q=<query>&format=jsonv2&limit=1`, a required `User-Agent` header (Nominatim's usage policy rejects unidentified clients), 3 retry attempts via `tenacity.Retrying` (same shape as `agents/llm_call.py`'s retry block — small enough not to warrant sharing an abstraction across two call sites). Empty result list → `GeocodingError`.

### `agents/facilities.py`

```python
class FacilityLookupError(Exception):
    """Raised when the Overpass query fails after all retries."""

def find_nearby_facilities(geo: GeoPoint) -> list[NearbyFacility]:
    """Queries Overpass for schools, hospitals, markets, and metro/transit
    stations near geo, computes haversine distance to each, and returns
    the closest 2 per type (closest 1 for metro). Raises
    FacilityLookupError on failure."""

def haversine_km(a: GeoPoint, b: GeoPoint) -> float:
    """Great-circle distance between two points in kilometers."""
```

Calls `POST {OVERPASS_BASE_URL}` with an Overpass QL query centered on `geo`:

```
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
```

Tag → `facility_type` mapping: `amenity=school`→`"school"`, `amenity=hospital`/`amenity=clinic`→`"hospital"`, `shop=supermarket`→`"market"`, `railway=station`/`public_transport=station`→`"metro"` (deduplicated by OSM element id, since a station can carry both tags). Elements missing a `name` tag are skipped (an unnamed node is not a useful "ask the broker about X" landmark). 3 retry attempts, same pattern as geocoding. Overpass returning zero elements is NOT an error (a genuinely remote property may have nothing within radius) — returns an empty list, not `FacilityLookupError`; only network/HTTP/timeout failures after retries raise.

## Node changes

### `agents/supervisor.py`

The static `TARGET_AREAS` dictionary fast path (no network) stays completely unmodified — first check, unchanged.

For unmatched localities, the flow changes from "LLM invents locality + address + lat/lon in one call" to two steps:
1. LLM extracts `locality` + `structured_address` from listing text only (new prompt `EXTRACT_LOCALITY_PROMPT`, new schema `LocalityExtractionResult(locality: str, structured_address: str)` — `GeocodeResult` and `GEOCODE_PROMPT` are replaced, not kept alongside).
2. `geocode_address(structured_address or locality)` resolves real coordinates.

Either step failing (`LLMCallError` or `GeocodingError`) routes to the existing `fallback_address_resolution(listing_input, str(e))` — unchanged from Phase 1, already sets `used_fallback=True`. Successful resolution keeps `confidence=0.9` (same convention as the static-dict path — both are "resolved with a real source," not a guess).

### `agents/neighbourhood.py`

`RESOLVE_NEIGHBOURHOOD_PROMPT`, `NeighbourhoodResult`, and the LLM call are removed entirely. The `cached_locality_lookup(f"neighbourhood:{locality}", ...)` wrapper stays (cache key convention unchanged from Phase 1), but its compute function now calls `find_nearby_facilities(address_resolved.geo)` instead of asking an LLM. Closest metro (by haversine) becomes `metro_station`/`metro_distance_km`; all returned facilities populate the `facilities` list, from which `school_count`/`hospital_count`/`market_count` are derived exactly as today.

`FacilityLookupError` → existing `fallback_neighbourhood_analysis(locality, metro_station)`, unchanged from Phase 1 — the calling node still sets `used_fallback=True` itself (per Phase 1's established pattern, since that fallback function returns a plain tuple, not a model).

### Unchanged files

`agents/pricing.py`, `agents/vibe.py`, `agents/synthesis.py`, `agents/graph.py`, `agents/service.py`, `agents/cache.py`, `agents/llm_call.py`, `agents/state.py`, `agents/fallbacks.py` (its `fallback_address_resolution` and `fallback_neighbourhood_analysis` functions are reused as-is), `api/main.py`, `rendering/*` — no changes required. `agents/prompts.py` loses `GEOCODE_PROMPT` and `RESOLVE_NEIGHBOURHOOD_PROMPT`, gains `EXTRACT_LOCALITY_PROMPT`. `agents/schemas.py` loses `GeocodeResult` and `NeighbourhoodResult`/`FacilityResult`, gains `LocalityExtractionResult`.

## Config additions (`config/settings.py`)

```python
NOMINATIM_BASE_URL: str = Field(default="https://nominatim.openstreetmap.org")
OVERPASS_BASE_URL: str = Field(default="https://overpass-api.de/api/interpreter")
OSM_USER_AGENT: str = Field(default="RentalTruthTeller/1.0")
OSM_REQUEST_TIMEOUT_SECONDS: int = Field(default=10)
```

All have working public defaults — no `.env` changes required to run, unlike the LLM provider settings.

## Testing

Mock HTTP calls with `responses` (already pinned in `requirements.txt`, currently only used by the crawler's own tests) instead of hitting real Nominatim/Overpass — keeps tests fast, offline, and deterministic. Per module:
- `tests/test_geocoding.py`: successful geocode, empty-results → `GeocodingError`, network failure + retry → eventual `GeocodingError`.
- `tests/test_facilities.py`: successful query with mixed facility types (including a railway=station/public_transport=station duplicate to verify dedup), empty-results → empty list (not an error), network failure + retry → `FacilityLookupError`, haversine distance correctness against a known reference pair of coordinates.
- `tests/test_supervisor.py` / `tests/test_neighbourhood.py`: updated to mock `geocode_address`/`find_nearby_facilities` directly (monkeypatch) rather than mocking `get_llm`'s geocode/neighbourhood LLM calls, since those calls no longer exist in these two nodes' facility/coordinate paths. `supervisor_node`'s LLM mock now only covers `LocalityExtractionResult`.

## Out of scope (explicitly deferred)

- Nominatim's documented 1 req/sec rate-limit policy: not enforced with a rate limiter. Real traffic to it only happens for localities outside `TARGET_AREAS` and outside the Phase 1 cache, which should be rare given Bangalore's limited set of common localities — added complexity isn't justified yet. Revisit if usage data says otherwise.
- Retrying `geocode_address` with just `locality` if `structured_address` yields no match — single-query, no cascading fallback strategy. `fallback_address_resolution` is the safety net.
- UI confidence badge (Phase 4).
- Anything about `.env`/API keys — this phase deliberately needs none.
