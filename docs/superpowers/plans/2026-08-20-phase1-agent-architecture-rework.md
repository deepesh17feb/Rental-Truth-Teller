# Phase 1: Agent Architecture Rework — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hand-rolled sequential `SequentialGraph` in `agents/graph.py` with a real `langgraph.StateGraph` that runs Pricing/Vibe/Neighbourhood concurrently, replace fragile manual JSON string-scraping with `PydanticOutputParser`-based structured output, add retry-with-backoff around every LLM call, add locality-scoped caching for benchmark/facility lookups, and add a `used_fallback` flag to every sub-agent's output model so callers (UI/API) can tell degraded fallback data from verified data.

**Architecture:** Two new shared modules (`agents/llm_call.py` for structured-output + retry, `agents/cache.py` for locality-scoped TTL caching) plus a new `agents/schemas.py` defining the LLM-facing output shape for each prompt. Every existing node (`supervisor.py`, `pricing.py`, `vibe.py`, `neighbourhood.py`, `synthesis.py`) is modified to call the new shared helper instead of `parse_json_from_llm`. `agents/graph.py` is rebuilt on `StateGraph` with real fan-out (Supervisor → {Pricing, Vibe, Neighbourhood} in parallel) and fan-in (→ Synthesis). Node function signatures (`def node(state: AgentState) -> dict`) do not change — `agents/state.py`'s `AgentState` TypedDict already has `messages: Annotated[List[str], add]`, which is the LangGraph reducer needed for concurrent branches to append to the same list without conflict, so it was already LangGraph-ready.

**Tech Stack:** `langgraph==0.0.51` (installed), `langchain-core==0.1.53` (installed), `tenacity==8.3.0` (installed, currently unused), `cachetools==7.1.4` (installed transitively, not yet pinned in `requirements.txt`), `pydantic==2.13.4`.

**Spec:** `plan.md` (repo root), section "Phase 1 — Agent Architecture Rework". This implementation plan also folds in the `used_fallback` visibility item, which `plan.md` lists under Phase 1 item 5.

## Global Constraints

- Do not touch `tests/test_items.py` — it is broken (imports non-existent `crawler.spiders.base_spider`) and Phase 0 (which would fix it) was explicitly skipped for this round. Every `pytest` invocation in this plan targets specific test files, never bare `pytest tests/`, so the pre-existing collection error never blocks these tasks.
- Do not change `AgentState`'s existing keys or the node function signature `def node(state: AgentState) -> dict`. Downstream code (`agents/service.py`, `api/main.py`, `rendering/ui/app.py`, `rendering/cli/run_truth_teller.py`) all depend on this shape and must keep working unmodified.
- New code must be testable without live LLM/Elasticsearch credentials — every test in this plan uses fakes/mocks (`langchain_core.runnables.RunnableLambda`, `unittest.mock.monkeypatch`), never a real API call.
- Add `cachetools` to `requirements.txt` (it's present in the venv transitively but not pinned — pin it so `pip install -r requirements.txt` alone is sufficient going forward).
- Keep using the existing `agents/config.py::get_response_text` helper for extracting text from LLM responses — don't reinvent it.

---

### Task 1: Locality-scoped TTL cache

**Files:**
- Create: `agents/cache.py`
- Test: `tests/test_cache.py`
- Modify: `requirements.txt` (add `cachetools==5.5.0` line under a new "Caching" section, near "Retry / Resilience")

**Interfaces:**
- Produces: `cached_locality_lookup(cache_key: str, compute_fn: Callable[[], T]) -> T`, `clear_locality_cache() -> None` — both used by `agents/pricing.py` and `agents/neighbourhood.py` in later tasks.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cache.py
from agents.cache import cached_locality_lookup, clear_locality_cache


def test_cached_locality_lookup_calls_compute_fn_once_per_key():
    clear_locality_cache()
    calls = {"n": 0}

    def compute():
        calls["n"] += 1
        return f"result-{calls['n']}"

    first = cached_locality_lookup("Whitefield", compute)
    second = cached_locality_lookup("Whitefield", compute)

    assert first == "result-1"
    assert second == "result-1"
    assert calls["n"] == 1


def test_cached_locality_lookup_different_keys_both_compute():
    clear_locality_cache()
    calls = {"n": 0}

    def compute():
        calls["n"] += 1
        return calls["n"]

    a = cached_locality_lookup("Koramangala", compute)
    b = cached_locality_lookup("Indiranagar", compute)

    assert a == 1
    assert b == 2
    assert calls["n"] == 2


def test_clear_locality_cache_resets_state():
    clear_locality_cache()
    calls = {"n": 0}

    def compute():
        calls["n"] += 1
        return calls["n"]

    cached_locality_lookup("HSR Layout", compute)
    clear_locality_cache()
    cached_locality_lookup("HSR Layout", compute)

    assert calls["n"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/deepeshmw_google_com/github/Rental-Truth-Teller && source .venv/bin/activate && PYTHONPATH=. python -m pytest tests/test_cache.py -v`
Expected: FAIL/ERROR with `ModuleNotFoundError: No module named 'agents.cache'`

- [ ] **Step 3: Write minimal implementation**

```python
# agents/cache.py
"""
agents/cache.py
────────────────
Locality-scoped TTL cache for LLM lookups that only depend on a Bangalore
locality name (pricing benchmarks, neighbourhood facilities), not on the
full listing text. Avoids re-asking the LLM the same question for every
request in the same area.
"""

from __future__ import annotations

from typing import Callable, TypeVar

from cachetools import TTLCache

T = TypeVar("T")

_locality_cache: TTLCache = TTLCache(maxsize=256, ttl=3600)


def cached_locality_lookup(cache_key: str, compute_fn: Callable[[], T]) -> T:
    """Returns the cached value for cache_key if present; otherwise calls
    compute_fn(), stores the result, and returns it."""
    if cache_key in _locality_cache:
        return _locality_cache[cache_key]
    value = compute_fn()
    _locality_cache[cache_key] = value
    return value


def clear_locality_cache() -> None:
    """Clears all cached entries. Used by tests to avoid cross-test pollution."""
    _locality_cache.clear()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. python -m pytest tests/test_cache.py -v`
Expected: 3 passed

- [ ] **Step 5: Pin cachetools in requirements.txt**

In `requirements.txt`, add a new section after the "Retry / Resilience" section (after the `tenacity==8.3.0` line):

```
# Caching
cachetools==5.5.0
```

- [ ] **Step 6: Commit**

```bash
git add agents/cache.py tests/test_cache.py requirements.txt
git commit -m "feat: add locality-scoped TTL cache for LLM lookups"
```

---

### Task 2: LLM output schemas

**Files:**
- Create: `agents/schemas.py`
- Test: `tests/test_schemas.py`

**Interfaces:**
- Produces: `GeocodeResult`, `FinancialsResult`, `BenchmarksResult`, `VibeResult`, `FacilityResult`, `NeighbourhoodResult`, `SynthesisResult` — pydantic models used by `agents/llm_call.py::call_llm_structured` in Task 3, and by every node module from Task 6 onward.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_schemas.py
import pytest
from pydantic import ValidationError

from agents.schemas import (
    GeocodeResult,
    FinancialsResult,
    BenchmarksResult,
    VibeResult,
    FacilityResult,
    NeighbourhoodResult,
    SynthesisResult,
)


def test_geocode_result_requires_lat_lon():
    result = GeocodeResult(
        locality="Whitefield",
        structured_address="Whitefield, Bangalore, Karnataka",
        lat=12.9698,
        lon=77.7500,
    )
    assert result.lat == 12.9698

    with pytest.raises(ValidationError):
        GeocodeResult(locality="Whitefield", structured_address="x")


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


def test_neighbourhood_result_with_facilities():
    result = NeighbourhoodResult(
        metro_station="Whitefield Metro",
        metro_distance_km=1.2,
        facilities=[
            FacilityResult(name="Test School", facility_type="school", distance_km=0.8)
        ],
    )
    assert len(result.facilities) == 1
    assert result.facilities[0].facility_type == "school"


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
Expected: FAIL/ERROR with `ModuleNotFoundError: No module named 'agents.schemas'`

- [ ] **Step 3: Write minimal implementation**

```python
# agents/schemas.py
"""
agents/schemas.py
──────────────────
Pydantic models describing the exact JSON shape each LLM prompt in
agents/prompts.py must return. Used with PydanticOutputParser (see
agents/llm_call.py) instead of hand-rolled JSON string scraping.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class GeocodeResult(BaseModel):
    locality: str = Field(description="Target locality or area name in Bangalore, e.g. Whitefield, Koramangala")
    structured_address: str = Field(description="Cleaned, structured address string ending in Bangalore, Karnataka")
    lat: float = Field(description="Estimated latitude for this locality in Bangalore")
    lon: float = Field(description="Estimated longitude for this locality in Bangalore")


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


class FacilityResult(BaseModel):
    name: str = Field(description="Name of the nearby facility")
    facility_type: str = Field(description="One of: school, hospital, metro, market")
    distance_km: float = Field(description="Realistic road distance in kilometers")


class NeighbourhoodResult(BaseModel):
    metro_station: str = Field(description="Name of the closest metro station")
    metro_distance_km: float = Field(description="Realistic road distance to the closest metro station in kilometers")
    facilities: List[FacilityResult] = Field(default_factory=list, description="List of nearby schools, hospitals, and markets")


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
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add agents/schemas.py tests/test_schemas.py
git commit -m "feat: add pydantic schemas for LLM structured output"
```

---

### Task 3: Structured-output + retry LLM call helper

**Files:**
- Create: `agents/llm_call.py`
- Test: `tests/test_llm_call.py`

**Interfaces:**
- Consumes: any pydantic `BaseModel` subclass from `agents/schemas.py` (Task 2) as `output_schema`; any `BaseChatModel`-like Runnable as `llm`.
- Produces: `call_llm_structured(llm, prompt_template: str, input_vars: dict, output_schema: Type[T], max_attempts: int = 3, wait_min: float = 1.0, wait_max: float = 8.0) -> T` and `LLMCallError` exception — used by every node module from Task 6 onward.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_llm_call.py
import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from agents.llm_call import call_llm_structured, LLMCallError
from agents.schemas import BenchmarksResult


def test_call_llm_structured_success():
    fake_llm = RunnableLambda(
        lambda _: AIMessage(content='{"avg_price_per_sqft": 42.0, "std_price_per_sqft": 6.0}')
    )

    result = call_llm_structured(
        fake_llm, "Locality: {locality}", {"locality": "Whitefield"}, BenchmarksResult
    )

    assert result.avg_price_per_sqft == 42.0
    assert result.std_price_per_sqft == 6.0


def test_call_llm_structured_retries_then_succeeds():
    calls = {"n": 0}

    def fake_invoke(_prompt_value):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("transient network error")
        return AIMessage(content='{"avg_price_per_sqft": 42.0, "std_price_per_sqft": 6.0}')

    fake_llm = RunnableLambda(fake_invoke)

    result = call_llm_structured(
        fake_llm,
        "Locality: {locality}",
        {"locality": "X"},
        BenchmarksResult,
        wait_min=0.01,
        wait_max=0.05,
    )

    assert calls["n"] == 3
    assert result.avg_price_per_sqft == 42.0


def test_call_llm_structured_raises_after_max_attempts():
    fake_llm = RunnableLambda(lambda _: (_ for _ in ()).throw(RuntimeError("boom")))

    with pytest.raises(LLMCallError):
        call_llm_structured(
            fake_llm,
            "Locality: {locality}",
            {"locality": "X"},
            BenchmarksResult,
            max_attempts=2,
            wait_min=0.01,
            wait_max=0.05,
        )


def test_call_llm_structured_malformed_json_raises_after_retries():
    fake_llm = RunnableLambda(lambda _: AIMessage(content="not json at all"))

    with pytest.raises(LLMCallError):
        call_llm_structured(
            fake_llm,
            "Locality: {locality}",
            {"locality": "X"},
            BenchmarksResult,
            max_attempts=2,
            wait_min=0.01,
            wait_max=0.05,
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. python -m pytest tests/test_llm_call.py -v`
Expected: FAIL/ERROR with `ModuleNotFoundError: No module named 'agents.llm_call'`

- [ ] **Step 3: Write minimal implementation**

```python
# agents/llm_call.py
"""
agents/llm_call.py
────────────────────
Shared helper for calling an LLM with a prompt template, parsing the
response into a pydantic schema via PydanticOutputParser, and retrying
with exponential backoff on any failure (network error or parse failure).
Replaces the old hand-rolled agents/utils.py::parse_json_from_llm pattern.
"""

from __future__ import annotations

import logging
from typing import Type, TypeVar

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel
from tenacity import Retrying, stop_after_attempt, wait_exponential

from agents.config import get_response_text

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMCallError(Exception):
    """Raised when a structured LLM call fails after all retry attempts."""


def call_llm_structured(
    llm: BaseChatModel,
    prompt_template: str,
    input_vars: dict,
    output_schema: Type[T],
    max_attempts: int = 3,
    wait_min: float = 1.0,
    wait_max: float = 8.0,
) -> T:
    """Invokes `llm` with `prompt_template` filled by `input_vars`, parses the
    response into `output_schema`, retrying up to `max_attempts` times with
    exponential backoff on any failure. Raises LLMCallError if every
    attempt fails."""
    parser = PydanticOutputParser(pydantic_object=output_schema)
    prompt = ChatPromptTemplate.from_template(
        prompt_template + "\n\n{format_instructions}"
    ).partial(format_instructions=parser.get_format_instructions())
    chain = prompt | llm

    def _call() -> T:
        response = chain.invoke(input_vars)
        text = get_response_text(response)
        return parser.parse(text)

    retryer = Retrying(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=wait_min, min=wait_min, max=wait_max),
        reraise=True,
    )
    try:
        return retryer(_call)
    except Exception as e:
        log.error(f"[call_llm_structured] Failed after {max_attempts} attempts: {e}")
        raise LLMCallError(str(e)) from e
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. python -m pytest tests/test_llm_call.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add agents/llm_call.py tests/test_llm_call.py
git commit -m "feat: add structured-output LLM call helper with retry"
```

---

### Task 4: `used_fallback` visibility on state models

**Files:**
- Modify: `agents/state.py:18-25` (`AddressResolved`), `agents/state.py:27-37` (`PricingAnalysis`), `agents/state.py:40-45` (`VibeAnalysis`), `agents/state.py:53-60` (`NeighbourhoodAnalysis`), `agents/state.py:63-71` (`VerdictCard`)
- Modify: `agents/fallbacks.py` (all four fallback functions)
- Test: `tests/test_fallbacks.py`

**Interfaces:**
- Produces: `used_fallback: bool` field (default `False`) on `AddressResolved`, `PricingAnalysis`, `VibeAnalysis`, `NeighbourhoodAnalysis`, `VerdictCard` — read by later node tasks and eventually by the UI (Phase 4, out of scope here).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_fallbacks.py
from agents.fallbacks import (
    fallback_address_resolution,
    fallback_vibe_analysis,
    fallback_neighbourhood_analysis,
    fallback_synthesis,
)


def test_fallback_address_resolution_flags_used_fallback():
    result = fallback_address_resolution("some listing", "boom")
    assert result["address_resolved"].used_fallback is True


def test_fallback_vibe_analysis_flags_used_fallback():
    result = fallback_vibe_analysis("boom")
    assert result["vibe_data"].used_fallback is True


def test_fallback_neighbourhood_analysis_returns_facilities():
    base_metro_dist, facilities = fallback_neighbourhood_analysis("Whitefield", "Whitefield Metro Station")
    assert base_metro_dist == 1.5
    assert len(facilities) == 4


def test_fallback_synthesis_flags_used_fallback():
    result = fallback_synthesis(rent=50000.0, overpriced_percentage=5.0, total_upfront_cost=150000.0, error_msg="boom")
    assert result["final_verdict"].used_fallback is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. python -m pytest tests/test_fallbacks.py -v`
Expected: FAIL — `AttributeError: 'AddressResolved' object has no attribute 'used_fallback'` (or similar) on the first assertion

- [ ] **Step 3: Add `used_fallback` field to each model in `agents/state.py`**

In `agents/state.py`, add `used_fallback: bool = False` as the last field of each of these five classes:

```python
class AddressResolved(BaseModel):
    raw_address: str
    structured_address: str = ""
    locality: str = ""
    city: str = "Bangalore"
    geo: Optional[GeoPoint] = None
    confidence: float = 1.0
    used_fallback: bool = False
```

```python
class PricingAnalysis(BaseModel):
    rent_amount: float = 0.0
    deposit_amount: float = 0.0
    deposit_multiplier: float = 0.0
    deposit_is_normal: bool = True
    area_sqft: Optional[float] = None
    price_per_sqft: Optional[float] = None
    market_avg_price_per_sqft: float = 0.0
    market_std_price_per_sqft: float = 0.0
    overpriced_percentage: float = 0.0
    price_drift_flag: bool = False
    used_fallback: bool = False
```

```python
class VibeAnalysis(BaseModel):
    amenity_vs_claim_diffs: List[str] = Field(default_factory=list)
    community_signals: List[str] = Field(default_factory=list)
    diet_pet_lifestyle: List[str] = Field(default_factory=list)
    listing_nlp_sentiment: str = "Neutral"
    used_fallback: bool = False
```

```python
class NeighbourhoodAnalysis(BaseModel):
    facilities: List[NearbyFacility] = Field(default_factory=list)
    metro_station: str = ""
    metro_distance_km: float = -1.0
    school_count: int = 0
    hospital_count: int = 0
    market_count: int = 0
    kibana_maps_pin_url: str = ""
    used_fallback: bool = False
```

```python
class VerdictCard(BaseModel):
    fair_range_min: float = 0.0
    fair_range_max: float = 0.0
    overpriced_percentage: float = 0.0
    total_upfront_cost: float = 0.0
    red_flags: List[str] = Field(default_factory=list)
    neighbourhood_score: float = 0.0
    broker_questionnaire: List[str] = Field(default_factory=list)
    used_fallback: bool = False
```

- [ ] **Step 4: Set `used_fallback=True` in `agents/fallbacks.py`**

Replace the full file contents:

```python
# agents/fallbacks.py
from agents.state import AddressResolved, GeoPoint, PricingAnalysis, VibeAnalysis, NearbyFacility, NeighbourhoodAnalysis, VerdictCard

def fallback_address_resolution(listing_input: str, error_msg: str) -> dict:
    """Fallback for Supervisor Agent geocoding."""
    fallback = AddressResolved(
        raw_address=listing_input[:100],
        structured_address="Whitefield, Bangalore, Karnataka",
        locality="Whitefield",
        geo=GeoPoint(lat=12.9698, lon=77.7500),
        confidence=0.4,
        used_fallback=True
    )
    return {
        "address_resolved": fallback,
        "messages": [f"[Supervisor Agent] Geocoding fallback used: {error_msg}"]
    }

def fallback_vibe_analysis(error_msg: str) -> dict:
    """Fallback for Vibe Check Agent."""
    return {
        "vibe_data": VibeAnalysis(
            amenity_vs_claim_diffs=["Unable to perform description NLP validation due to exception."],
            community_signals=[],
            diet_pet_lifestyle=[],
            listing_nlp_sentiment="Error",
            used_fallback=True
        ),
        "messages": [f"[Vibe Check Agent] Error encountered: {error_msg}"]
    }

def fallback_neighbourhood_analysis(locality: str, metro_station: str) -> tuple[float, list[NearbyFacility]]:
    """Fallback logic for Neighbourhood Agent POIs."""
    base_metro_dist = 1.5
    facilities = [
        NearbyFacility(name=f"{locality} Central High School", facility_type="school", distance_km=1.2),
        NearbyFacility(name=f"{locality} Community Clinic", facility_type="hospital", distance_km=0.8),
        NearbyFacility(name=f"{locality} Supermarket", facility_type="market", distance_km=0.5),
        NearbyFacility(name=metro_station, facility_type="metro", distance_km=base_metro_dist)
    ]
    return base_metro_dist, facilities

def fallback_synthesis(rent: float, overpriced_percentage: float, total_upfront_cost: float, error_msg: str) -> dict:
    """Fallback for Synthesis Agent Verdict Card."""
    flat_verdict = VerdictCard(
        fair_range_min=rent * 0.85,
        fair_range_max=rent * 1.15,
        overpriced_percentage=overpriced_percentage,
        total_upfront_cost=total_upfront_cost,
        red_flags=["Failed to run composite synthesis, showing structural pricing alerts only."],
        neighbourhood_score=6.0,
        broker_questionnaire=["Why does the landlord charge this amount of rent?"],
        used_fallback=True
    )
    return {
        "final_verdict": flat_verdict,
        "messages": [f"[Synthesis Agent] Synthesis error fallback: {error_msg}"]
    }
```

Note: `fallback_neighbourhood_analysis` keeps returning a plain tuple (unchanged shape) — it's called from inside `neighbourhood_node`, which builds the final `NeighbourhoodAnalysis` object itself. Task 9 sets `used_fallback=True` there directly.

- [ ] **Step 5: Run test to verify it passes**

Run: `PYTHONPATH=. python -m pytest tests/test_fallbacks.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add agents/state.py agents/fallbacks.py tests/test_fallbacks.py
git commit -m "feat: add used_fallback flag to agent output models"
```

---

### Task 5: Strip manual JSON instructions from prompts

**Files:**
- Modify: `agents/prompts.py` (all six prompt constants)
- Test: `tests/test_prompts.py`

**Why:** `agents/llm_call.py::call_llm_structured` (Task 3) already appends `PydanticOutputParser`'s own `{format_instructions}` block to every prompt. Leaving the old hand-written "Return a strictly formatted JSON object... Write ONLY the raw JSON" instructions in place would give the model two different, possibly conflicting schema descriptions for the same call.

**Interfaces:**
- Consumes: nothing new.
- Produces: same six prompt constant names (`GEOCODE_PROMPT`, `EXTRACT_FINANCIALS_PROMPT`, `ESTIMATE_BENCHMARKS_PROMPT`, `VIBE_CHECK_PROMPT`, `RESOLVE_NEIGHBOURHOOD_PROMPT`, `SYNTHESIS_PROMPT`), now without embedded JSON schema examples — consumed by every node task from Task 6 onward.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_prompts.py
from agents import prompts

ALL_PROMPTS = [
    prompts.GEOCODE_PROMPT,
    prompts.EXTRACT_FINANCIALS_PROMPT,
    prompts.ESTIMATE_BENCHMARKS_PROMPT,
    prompts.VIBE_CHECK_PROMPT,
    prompts.RESOLVE_NEIGHBOURHOOD_PROMPT,
    prompts.SYNTHESIS_PROMPT,
]


def test_prompts_no_longer_hand_roll_json_instructions():
    for prompt in ALL_PROMPTS:
        assert "raw JSON" not in prompt
        assert "```" not in prompt


def test_prompts_still_have_their_input_variables():
    assert "{listing_input}" in prompts.GEOCODE_PROMPT
    assert "{listing_input}" in prompts.EXTRACT_FINANCIALS_PROMPT
    assert "{locality}" in prompts.ESTIMATE_BENCHMARKS_PROMPT
    assert "{listing_input}" in prompts.VIBE_CHECK_PROMPT
    assert "{locality}" in prompts.RESOLVE_NEIGHBOURHOOD_PROMPT
    assert "{structured_address}" in prompts.RESOLVE_NEIGHBOURHOOD_PROMPT
    assert "{address_resolved}" in prompts.SYNTHESIS_PROMPT
    assert "{pricing_data}" in prompts.SYNTHESIS_PROMPT
    assert "{vibe_data}" in prompts.SYNTHESIS_PROMPT
    assert "{neighbourhood_data}" in prompts.SYNTHESIS_PROMPT
    assert "{critique_section}" in prompts.SYNTHESIS_PROMPT
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. python -m pytest tests/test_prompts.py -v`
Expected: FAIL on `test_prompts_no_longer_hand_roll_json_instructions` (current prompts contain "raw JSON" and backtick-fenced examples)

- [ ] **Step 3: Replace `agents/prompts.py` contents**

```python
# agents/prompts.py
GEOCODE_PROMPT = """You are a Bangalore spatial resolver agent.
Analyze the given rental property listing content and extract:
1. The target locality or area in Bangalore (e.g. Whitefield, Koramangala, Indiranagar, HSR Layout).
2. A cleaned, structured address.
3. A sensible latitude/longitude geopoint estimate for this locality in Bangalore.

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

RESOLVE_NEIGHBOURHOOD_PROMPT = """You are a Bangalore local geographer and spatial intelligence agent.
Given a target property's resolved locality and structured address:
Locality: {locality}
Structured Address: {structured_address}

Resolve real, actual nearby facilities of the following types that exist around this area:
1. The closest real Metro Station and its realistic road distance in kilometers (usually 0.5 to 5.0 km).
2. Two real schools (within 3km) and their realistic distances.
3. Two real hospitals or clinics (within 3km) and their realistic distances.
4. Two real supermarkets or local shopping markets (within 2km) and their realistic distances.
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
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add agents/prompts.py tests/test_prompts.py
git commit -m "refactor: strip hand-rolled JSON instructions from prompts"
```

---

### Task 6: Rewire `agents/supervisor.py`

**Files:**
- Modify: `agents/supervisor.py:1-85` (whole file)
- Test: `tests/test_supervisor.py`

**Interfaces:**
- Consumes: `call_llm_structured`, `LLMCallError` (Task 3); `GeocodeResult` (Task 2); `fallback_address_resolution` (Task 4, unchanged signature).
- Produces: unchanged — `supervisor_node(state: AgentState) -> dict` with keys `address_resolved`, `messages`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_supervisor.py
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

import agents.supervisor as supervisor_mod
from agents.state import AgentState


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


def test_supervisor_falls_through_to_llm_geocoding_for_unknown_locality(monkeypatch):
    fake_llm = RunnableLambda(
        lambda _: AIMessage(
            content='{"locality": "JP Nagar", "structured_address": "JP Nagar, Bangalore, Karnataka", "lat": 12.9077, "lon": 77.5928}'
        )
    )
    monkeypatch.setattr(supervisor_mod, "get_llm", lambda temperature=0.1: fake_llm)

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. python -m pytest tests/test_supervisor.py -v`
Expected: FAIL — `test_supervisor_uses_fallback_when_llm_call_fails` and `test_supervisor_falls_through_to_llm_geocoding_for_unknown_locality` fail because `supervisor_mod` has no `get_llm` attribute to monkeypatch under the new import shape yet (or, before Step 3, the old code raises `json.JSONDecodeError` instead of using retries — the fallback test may pass by accident but the LLM-geocode-success test fails since the fake response can't be parsed by the old `parse_json_from_llm`/`ChatPromptTemplate` combo consistently). Confirm actual failure output, then proceed.

- [ ] **Step 3: Replace `agents/supervisor.py` contents**

```python
# agents/supervisor.py
"""
agents/supervisor.py
────────────────────
Supervisor Agent: First entrypoint. Performs geocoding / address resolution 
from raw listing input text to populate shared agent parameters.
"""

from __future__ import annotations

import logging
from agents.config import get_llm
from agents.prompts import GEOCODE_PROMPT
from agents.state import AgentState, AddressResolved, GeoPoint
from agents.fallbacks import fallback_address_resolution
from agents.llm_call import call_llm_structured, LLMCallError
from agents.schemas import GeocodeResult

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

    # Look up known target areas (from config.areas) before falling back to LLM geocoding
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
        data = call_llm_structured(llm, GEOCODE_PROMPT, {"listing_input": listing_input}, GeocodeResult)

        resolved = AddressResolved(
            raw_address=listing_input[:100],
            structured_address=data.structured_address,
            locality=data.locality,
            geo=GeoPoint(lat=data.lat, lon=data.lon),
            confidence=0.9
        )

        msg = f"[Supervisor Agent] Geolocated to `{resolved.locality}`. Coords: ({resolved.geo.lat}, {resolved.geo.lon})."
        log.info(msg)
        return {
            "address_resolved": resolved,
            "messages": [msg]
        }
    except LLMCallError as e:
        log.error(f"[Supervisor Agent] Address resolution failed after retries: {e}")
        return fallback_address_resolution(listing_input, str(e))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. python -m pytest tests/test_supervisor.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add agents/supervisor.py tests/test_supervisor.py
git commit -m "refactor: use structured-output LLM helper in supervisor agent"
```

---

### Task 7: Rewire `agents/pricing.py`

**Files:**
- Modify: `agents/pricing.py:1-206` (whole file)
- Test: `tests/test_pricing.py`

**Interfaces:**
- Consumes: `call_llm_structured`, `LLMCallError` (Task 3); `FinancialsResult`, `BenchmarksResult` (Task 2); `cached_locality_lookup` (Task 1).
- Produces: unchanged — `pricing_node(state: AgentState) -> dict` with keys `pricing_data`, `messages`; `PricingAnalysis.used_fallback` now set correctly.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pricing.py
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

import agents.pricing as pricing_mod
from agents.cache import clear_locality_cache
from agents.state import AgentState, AddressResolved, GeoPoint


def _state_with_locality(locality: str, listing_input: str) -> AgentState:
    return {
        "listing_input": listing_input,
        "address_resolved": AddressResolved(
            raw_address=listing_input,
            locality=locality,
            geo=GeoPoint(lat=12.97, lon=77.75),
        ),
        "pricing_data": None,
        "vibe_data": None,
        "neighbourhood_data": None,
        "final_verdict": None,
        "messages": [],
    }


def test_pricing_uses_llm_benchmarks_and_caches_by_locality(monkeypatch):
    clear_locality_cache()
    monkeypatch.setattr(
        pricing_mod, "get_elasticsearch_client", lambda: (_ for _ in ()).throw(RuntimeError("no ES"))
    )
    monkeypatch.setattr("glob.glob", lambda pattern: [])

    benchmark_calls = {"n": 0}

    def dispatch(prompt_value):
        text = prompt_value.to_string()
        if "financial extractor" in text.lower():
            return AIMessage(content='{"rent": 50000, "deposit": 300000, "area_sqft": 1000}')
        benchmark_calls["n"] += 1
        return AIMessage(content='{"avg_price_per_sqft": 45.0, "std_price_per_sqft": 5.0}')

    monkeypatch.setattr(pricing_mod, "get_llm", lambda temperature=0.1: RunnableLambda(dispatch))

    state = _state_with_locality("Whitefield", "2BHK in Whitefield, rent 50000")

    result1 = pricing_mod.pricing_node(state)
    result2 = pricing_mod.pricing_node(state)

    assert result1["pricing_data"].market_avg_price_per_sqft == 45.0
    assert result2["pricing_data"].market_avg_price_per_sqft == 45.0
    assert result1["pricing_data"].used_fallback is False
    assert benchmark_calls["n"] == 1  # second pricing_node call hit the cache


def test_pricing_sets_used_fallback_when_llm_benchmarks_fail(monkeypatch):
    clear_locality_cache()
    monkeypatch.setattr(
        pricing_mod, "get_elasticsearch_client", lambda: (_ for _ in ()).throw(RuntimeError("no ES"))
    )
    monkeypatch.setattr("glob.glob", lambda pattern: [])

    def dispatch(prompt_value):
        text = prompt_value.to_string()
        if "financial extractor" in text.lower():
            return AIMessage(content='{"rent": 50000, "deposit": 300000, "area_sqft": 1000}')
        raise RuntimeError("LLM down")

    monkeypatch.setattr(pricing_mod, "get_llm", lambda temperature=0.1: RunnableLambda(dispatch))

    state = _state_with_locality("Jayanagar", "2BHK in Jayanagar, rent 50000")
    result = pricing_mod.pricing_node(state)

    assert result["pricing_data"].used_fallback is True
    assert result["pricing_data"].market_avg_price_per_sqft == 40.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. python -m pytest tests/test_pricing.py -v`
Expected: FAIL — caching assertion fails (`benchmark_calls["n"] == 2`, not `1`) since the current code has no cache, and `used_fallback` attribute assertions fail since the field doesn't exist on `PricingAnalysis` construction yet in this file

- [ ] **Step 3: Replace `agents/pricing.py` contents**

```python
# agents/pricing.py
"""
agents/pricing.py
─────────────────
Pricing Agent: Performs market rate checks, deposit evaluations, and flags price drift
using hybrid Elasticsearch search.
"""

from __future__ import annotations

import logging
import math
from agents.config import get_llm, get_elasticsearch_client
from agents.prompts import EXTRACT_FINANCIALS_PROMPT, ESTIMATE_BENCHMARKS_PROMPT
from agents.state import AgentState, PricingAnalysis
from agents.llm_call import call_llm_structured, LLMCallError
from agents.schemas import FinancialsResult, BenchmarksResult
from agents.cache import cached_locality_lookup

log = logging.getLogger(__name__)

def pricing_node(state: AgentState) -> dict:
    log.info("[Pricing Agent] Analyzing Pricing, Deposit Norms, & Price Drift…")
    
    listing_input = state.get("listing_input", "")
    address_resolved = state.get("address_resolved")
    
    if not listing_input:
        return {"pricing_data": PricingAnalysis()}

    llm = get_llm(temperature=0.1)

    # 1. Parse client-side listing financials using LLM
    curr_rent = 0.0
    curr_deposit = 0.0
    curr_area = None
    financials_failed = False

    try:
        financials = call_llm_structured(llm, EXTRACT_FINANCIALS_PROMPT, {"listing_input": listing_input}, FinancialsResult)
        curr_rent = financials.rent
        curr_deposit = financials.deposit
        curr_area = financials.area_sqft
    except LLMCallError as e:
        log.error(f"[Pricing Agent] Financial extraction failed after retries: {e}")
        financials_failed = True

    # 2. Local market benchmarks: Resolve locality
    locality = address_resolved.locality if address_resolved else ""
    if not locality and address_resolved:
        locality = address_resolved.structured_address.split(",")[0]
    if not locality:
        locality = "Bangalore"
        
    market_avg = 40.0
    market_std = 7.0
    fetched_from_es = False
    used_fallback = False

    # 3. Query Elasticsearch for actual listing comparables
    es_ratings = []
    try:
        es = get_elasticsearch_client()
        search_body = {
            "query": {
                "bool": {
                    "must": [
                        {"match": {"transaction_type": "rent"}},
                    ],
                    "should": [
                        {"match": {"area": locality}},
                        {"match": {"address": locality}}
                    ]
                }
            },
            "size": 20
        }
        
        res = es.search(index="bangalore_properties", body=search_body)
        hits = res.get("hits", {}).get("hits", [])
        
        for hit in hits:
            source_doc = hit.get("_source", {})
            rent = source_doc.get("price")
            sqft = source_doc.get("area_sqft")
            if rent and sqft:
                es_ratings.append(float(rent) / float(sqft))
                
        if len(es_ratings) > 2:
            market_avg = sum(es_ratings) / len(es_ratings)
            variance = sum((x - market_avg) ** 2 for x in es_ratings) / len(es_ratings)
            market_std = math.sqrt(variance) if variance > 0 else 1.0
            fetched_from_es = True
            log.info(f"[Pricing Agent] ES search matched {len(es_ratings)} comparables. Calculated Mean Rate: Rs.{market_avg:.2f}/sqft, StdDev: {market_std:.2f}")
        else:
            log.info(f"[Pricing Agent] Insufficient ES comparables found ({len(es_ratings)}). Querying LLM for dynamic baseline metrics.")

    except Exception as exc:
        log.warning(f"[Pricing Agent] Elasticsearch connection failed: {exc}. Trying local embedded BM25 search.")
        
        try:
            import json
            import glob
            from rank_bm25 import BM25Okapi

            # Find latest jsonl
            list_of_files = glob.glob('output/*.jsonl')
            if list_of_files:
                latest_file = max(list_of_files, key=lambda x: x)
                local_docs = []
                with open(latest_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            local_docs.append(json.loads(line))
                
                # Filter by rent
                rent_docs = [doc for doc in local_docs if doc.get("transaction_type") == "rent"]
                
                if rent_docs:
                    # Create corpus
                    corpus = []
                    for doc in rent_docs:
                        text = f"{doc.get('area', '')} {doc.get('address', '')} {doc.get('description', '')}".lower()
                        corpus.append(text.split())
                        
                    bm25 = BM25Okapi(corpus)
                    query = locality.lower().split()
                    top_n = bm25.get_top_n(query, rent_docs, n=20)
                    
                    for doc in top_n:
                        rent = doc.get("price")
                        sqft = doc.get("area_sqft")
                        if rent and sqft:
                            es_ratings.append(float(rent) / float(sqft))
                    
                    if len(es_ratings) > 2:
                        market_avg = sum(es_ratings) / len(es_ratings)
                        variance = sum((x - market_avg) ** 2 for x in es_ratings) / len(es_ratings)
                        market_std = math.sqrt(variance) if variance > 0 else 1.0
                        fetched_from_es = True
                        log.info(f"[Pricing Agent] Local BM25 search matched {len(es_ratings)} comparables. Calculated Mean Rate: Rs.{market_avg:.2f}/sqft, StdDev: {market_std:.2f}")
                    else:
                        log.info(f"[Pricing Agent] Insufficient local comparables found ({len(es_ratings)}). Querying LLM for dynamic baseline metrics.")
        except Exception as local_exc:
            log.warning(f"[Pricing Agent] Local BM25 search also failed: {local_exc}. Querying LLM for dynamic benchmarks.")

    # Fallback to dynamic LLM benchmark resolution if ES search was sparse or failed
    if not fetched_from_es:
        try:
            def _fetch_benchmarks() -> BenchmarksResult:
                return call_llm_structured(llm, ESTIMATE_BENCHMARKS_PROMPT, {"locality": locality}, BenchmarksResult)

            benchmarks = cached_locality_lookup(f"benchmarks:{locality}", _fetch_benchmarks)
            market_avg = benchmarks.avg_price_per_sqft
            market_std = benchmarks.std_price_per_sqft
            log.info(f"[Pricing Agent] Resolved benchmarks dynamically via LLM for `{locality}` -> Avg: Rs.{market_avg}/sqft, StdDev: {market_std}")
        except LLMCallError as e:
            log.error(f"[Pricing Agent] Failed to fetch dynamic pricing benchmarks via LLM: {e}. Using global defaults.")
            market_avg = 40.0
            market_std = 7.0
            used_fallback = True

    # 4. Process pricing parameters
    curr_price_per_sqft = None
    overpriced_pct = 0.0
    price_drift = False
    
    if curr_area and curr_area > 0 and curr_rent > 0:
        curr_price_per_sqft = curr_rent / curr_area
        overpriced_pct = ((curr_price_per_sqft - market_avg) / market_avg) * 100.0
        # Price drift logic: Let's flag if rate exceeds average + 1.5 * stddev
        if curr_price_per_sqft > (market_avg + 1.5 * market_std):
            price_drift = True

    # 5. Deposit Multiplier validation (standard in Bangalore is 5 to 10 months rent)
    deposit_mult = 0.0
    deposit_normal = True
    if curr_rent > 0:
        deposit_mult = curr_deposit / curr_rent
        # Flag anormal if deposit represents > 10 months of rent
        if deposit_mult > 10.0:
            deposit_normal = False
            
    analysis_res = PricingAnalysis(
        rent_amount=curr_rent,
        deposit_amount=curr_deposit,
        deposit_multiplier=round(deposit_mult, 2),
        deposit_is_normal=deposit_normal,
        area_sqft=curr_area,
        price_per_sqft=round(curr_price_per_sqft, 2) if curr_price_per_sqft else None,
        market_avg_price_per_sqft=round(market_avg, 2),
        market_std_price_per_sqft=round(market_std, 2),
        overpriced_percentage=round(overpriced_pct, 1),
        price_drift_flag=price_drift,
        used_fallback=used_fallback or financials_failed
    )
    
    msg = f"[Pricing Agent] Completed. Rent: Rs.{curr_rent:.0f}, Security Dep: {deposit_mult:.1f}x Rent multiplier."
    log.info(msg)
    return {
        "pricing_data": analysis_res,
        "messages": [msg]
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. python -m pytest tests/test_pricing.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add agents/pricing.py tests/test_pricing.py
git commit -m "refactor: use structured-output LLM helper and locality cache in pricing agent"
```

---

### Task 8: Rewire `agents/vibe.py`

**Files:**
- Modify: `agents/vibe.py:1-50` (whole file)
- Test: `tests/test_vibe.py`

**Interfaces:**
- Consumes: `call_llm_structured`, `LLMCallError` (Task 3); `VibeResult` (Task 2); `fallback_vibe_analysis` (Task 4, unchanged signature).
- Produces: unchanged — `vibe_check_node(state: AgentState) -> dict` with keys `vibe_data`, `messages`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_vibe.py
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

import agents.vibe as vibe_mod
from agents.state import AgentState


def _state(listing_input: str) -> AgentState:
    return {
        "listing_input": listing_input,
        "address_resolved": None,
        "pricing_data": None,
        "vibe_data": None,
        "neighbourhood_data": None,
        "final_verdict": None,
        "messages": [],
    }


def test_vibe_check_success(monkeypatch):
    fake_llm = RunnableLambda(
        lambda _: AIMessage(
            content='{"amenity_vs_claim_diffs": ["claims metro nearby but 20 min walk"], "community_signals": ["family friendly"], "diet_pet_lifestyle": ["pure veg only"], "listing_nlp_sentiment": "Pressuring"}'
        )
    )
    monkeypatch.setattr(vibe_mod, "get_llm", lambda temperature=0.1: fake_llm)

    result = vibe_mod.vibe_check_node(_state("2BHK, pure veg only, near metro (20 min walk)"))

    assert result["vibe_data"].listing_nlp_sentiment == "Pressuring"
    assert result["vibe_data"].used_fallback is False
    assert "pure veg only" in result["vibe_data"].diet_pet_lifestyle


def test_vibe_check_uses_fallback_on_llm_failure(monkeypatch):
    fake_llm = RunnableLambda(lambda _: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(vibe_mod, "get_llm", lambda temperature=0.1: fake_llm)

    result = vibe_mod.vibe_check_node(_state("2BHK listing"))

    assert result["vibe_data"].used_fallback is True
    assert result["vibe_data"].listing_nlp_sentiment == "Error"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. python -m pytest tests/test_vibe.py -v`
Expected: FAIL — old code uses `parse_json_from_llm`/manual `ChatPromptTemplate` and has no `used_fallback` on `VibeAnalysis` construction path here yet

- [ ] **Step 3: Replace `agents/vibe.py` contents**

```python
# agents/vibe.py
"""
agents/vibe.py
──────────────
Vibe Check Agent: Analyzes listing text, community signals, lifestyle constraints.
"""

from __future__ import annotations

import logging
from agents.config import get_llm
from agents.prompts import VIBE_CHECK_PROMPT
from agents.state import AgentState, VibeAnalysis
from agents.fallbacks import fallback_vibe_analysis
from agents.llm_call import call_llm_structured, LLMCallError
from agents.schemas import VibeResult

log = logging.getLogger(__name__)

def vibe_check_node(state: AgentState) -> dict:
    """Analyze the listing for claims vs truth differences, tenant rules and vibes."""
    log.info("[Vibe Check Agent] Processing Listing Text…")
    
    listing_input = state.get("listing_input", "")
    if not listing_input:
        return {"vibe_data": VibeAnalysis()}

    llm = get_llm(temperature=0.1)

    try:
        data = call_llm_structured(llm, VIBE_CHECK_PROMPT, {"listing_input": listing_input}, VibeResult)

        vibe_res = VibeAnalysis(
            amenity_vs_claim_diffs=data.amenity_vs_claim_diffs,
            community_signals=data.community_signals,
            diet_pet_lifestyle=data.diet_pet_lifestyle,
            listing_nlp_sentiment=data.listing_nlp_sentiment
        )
        
        log.info(f"[Vibe Check Agent] Success. Sentiment: {vibe_res.listing_nlp_sentiment}")
        return {"vibe_data": vibe_res, "messages": ["[Vibe Check Agent] Successfully parsed listing description & rules."]}
    
    except LLMCallError as e:
        log.error(f"[Vibe Check Agent] Error executing vibe checker LLM: {e}")
        return fallback_vibe_analysis(str(e))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. python -m pytest tests/test_vibe.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add agents/vibe.py tests/test_vibe.py
git commit -m "refactor: use structured-output LLM helper in vibe agent"
```

---

### Task 9: Rewire `agents/neighbourhood.py`

**Files:**
- Modify: `agents/neighbourhood.py:1-97` (whole file)
- Test: `tests/test_neighbourhood.py`

**Interfaces:**
- Consumes: `call_llm_structured`, `LLMCallError` (Task 3); `NeighbourhoodResult` (Task 2); `cached_locality_lookup` (Task 1); `fallback_neighbourhood_analysis` (Task 4, unchanged signature).
- Produces: unchanged — `neighbourhood_node(state: AgentState) -> dict` with keys `neighbourhood_data`, `messages`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_neighbourhood.py
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

import agents.neighbourhood as neigh_mod
from agents.cache import clear_locality_cache
from agents.state import AgentState, AddressResolved, GeoPoint


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

    def dispatch(_prompt_value):
        calls["n"] += 1
        return AIMessage(
            content='{"metro_station": "Whitefield Metro", "metro_distance_km": 1.1, "facilities": [{"name": "Test School", "facility_type": "school", "distance_km": 0.9}]}'
        )

    monkeypatch.setattr(neigh_mod, "get_llm", lambda temperature=0.1: RunnableLambda(dispatch))

    result1 = neigh_mod.neighbourhood_node(_state("Whitefield"))
    result2 = neigh_mod.neighbourhood_node(_state("Whitefield"))

    assert result1["neighbourhood_data"].metro_station == "Whitefield Metro"
    assert result1["neighbourhood_data"].school_count == 1
    assert result1["neighbourhood_data"].used_fallback is False
    assert calls["n"] == 1  # second call hit the cache
    assert result2["neighbourhood_data"].metro_station == "Whitefield Metro"


def test_neighbourhood_uses_fallback_on_llm_failure(monkeypatch):
    clear_locality_cache()
    monkeypatch.setattr(
        neigh_mod, "get_llm", lambda temperature=0.1: RunnableLambda(lambda _: (_ for _ in ()).throw(RuntimeError("boom")))
    )

    result = neigh_mod.neighbourhood_node(_state("Jayanagar"))

    assert result["neighbourhood_data"].used_fallback is True
    assert result["neighbourhood_data"].school_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. python -m pytest tests/test_neighbourhood.py -v`
Expected: FAIL — caching assertion (`calls["n"] == 1`) fails against current uncached code, and `used_fallback` isn't set anywhere yet

- [ ] **Step 3: Replace `agents/neighbourhood.py` contents**

```python
# agents/neighbourhood.py
"""
agents/neighbourhood.py
───────────────────────
Neighbourhood Agent: Analyzes local facilities, calculate metro distances, schools, 
hospitals, and generates mock Kibana map pin layout.
"""

from __future__ import annotations

import logging
from agents.config import get_llm
from agents.prompts import RESOLVE_NEIGHBOURHOOD_PROMPT
from agents.state import AgentState, NearbyFacility, NeighbourhoodAnalysis
from agents.fallbacks import fallback_neighbourhood_analysis
from agents.llm_call import call_llm_structured, LLMCallError
from agents.schemas import NeighbourhoodResult
from agents.cache import cached_locality_lookup

log = logging.getLogger(__name__)

def neighbourhood_node(state: AgentState) -> dict:
    log.info("[Neighbourhood Agent] Analyzing neighborhood points of interest (POI) dynamically…")
    
    address_resolved = state.get("address_resolved")
    locality = address_resolved.locality if address_resolved else "Bangalore"
    structured_address = address_resolved.structured_address if address_resolved else "Bangalore, Karnataka"
    
    facilities = []
    metro_station = f"{locality} Metro Station"
    base_metro_dist = -1.0
    used_fallback = False

    llm = get_llm(temperature=0.1)

    try:
        def _fetch_neighbourhood() -> NeighbourhoodResult:
            return call_llm_structured(
                llm,
                RESOLVE_NEIGHBOURHOOD_PROMPT,
                {"locality": locality, "structured_address": structured_address},
                NeighbourhoodResult,
            )

        data = cached_locality_lookup(f"neighbourhood:{locality}", _fetch_neighbourhood)

        metro_station = data.metro_station
        base_metro_dist = data.metro_distance_km

        for f in data.facilities:
            facilities.append(NearbyFacility(name=f.name, facility_type=f.facility_type, distance_km=f.distance_km))

        # Append Metro Station as facility too
        facilities.append(NearbyFacility(
            name=metro_station,
            facility_type="metro",
            distance_km=base_metro_dist
        ))
        log.info(f"[Neighbourhood Agent] Resolved closest transit: {metro_station} ({base_metro_dist} km). Total POIs catalogued: {len(facilities)}")

    except LLMCallError as exc:
        log.error(f"[Neighbourhood Agent] Error during dynamic POI resolution: {exc}. Using robust fallback estimates.")
        base_metro_dist, facilities = fallback_neighbourhood_analysis(locality, metro_station)
        used_fallback = True

    # 2. Summarize metrics for State
    schools_count = sum(1 for f in facilities if f.facility_type == "school")
    hospitals_count = sum(1 for f in facilities if f.facility_type == "hospital")
    markets_count = sum(1 for f in facilities if f.facility_type == "market")
    
    lat = address_resolved.geo.lat if (address_resolved and address_resolved.geo) else 12.9716
    lon = address_resolved.geo.lon if (address_resolved and address_resolved.geo) else 77.5946
    
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

    msg = f"[Neighbourhood Agent] Dynamic POI Analysis completed. Metro: {metro_station} ({base_metro_dist}km)."
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
git commit -m "refactor: use structured-output LLM helper and locality cache in neighbourhood agent"
```

---

### Task 10: Rewire `agents/synthesis.py`

**Files:**
- Modify: `agents/synthesis.py:1-89` (whole file)
- Test: `tests/test_synthesis.py`

**Interfaces:**
- Consumes: `call_llm_structured`, `LLMCallError` (Task 3); `SynthesisResult` (Task 2); `fallback_synthesis` (Task 4, unchanged signature).
- Produces: unchanged — `synthesis_node(state: AgentState) -> dict` with keys `final_verdict`, `messages`.

Also fixes a pre-existing bug: the original code's red-flag "already present" checks compared against a *different* string than the one actually appended (e.g. checked for `"High price variance detected (above local average)"` but appended `"Property pricing is majorly drifted from local comparable averages."`), so the dedup check never matched anything it appended. This task makes the checked string and the appended string identical.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_synthesis.py
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

import agents.synthesis as synthesis_mod
from agents.state import AgentState, PricingAnalysis


def _state(pricing_data=None) -> AgentState:
    return {
        "listing_input": "listing",
        "address_resolved": None,
        "pricing_data": pricing_data,
        "vibe_data": None,
        "neighbourhood_data": None,
        "final_verdict": None,
        "messages": [],
    }


def test_synthesis_success(monkeypatch):
    fake_llm = RunnableLambda(
        lambda _: AIMessage(
            content='{"fair_range_min": 45000.0, "fair_range_max": 55000.0, "overpriced_percentage": 5.0, "red_flags": ["broker fee undisclosed"], "neighbourhood_score": 7.5, "broker_questionnaire": ["Why is deposit so high?"]}'
        )
    )
    monkeypatch.setattr(synthesis_mod, "get_llm", lambda temperature=0.1: fake_llm)

    pricing = PricingAnalysis(rent_amount=50000.0, deposit_amount=300000.0)
    result = synthesis_mod.synthesis_node(_state(pricing_data=pricing))

    verdict = result["final_verdict"]
    assert verdict.fair_range_min == 45000.0
    assert verdict.used_fallback is False
    assert verdict.total_upfront_cost == 50000.0 + 300000.0 + 50000.0


def test_synthesis_appends_price_drift_flag_exactly_once(monkeypatch):
    fake_llm = RunnableLambda(
        lambda _: AIMessage(
            content='{"fair_range_min": 45000.0, "fair_range_max": 55000.0, "overpriced_percentage": 40.0, "red_flags": [], "neighbourhood_score": 7.5, "broker_questionnaire": []}'
        )
    )
    monkeypatch.setattr(synthesis_mod, "get_llm", lambda temperature=0.1: fake_llm)

    pricing = PricingAnalysis(rent_amount=50000.0, deposit_amount=600000.0, price_drift_flag=True, deposit_is_normal=False, deposit_multiplier=12.0)
    result = synthesis_mod.synthesis_node(_state(pricing_data=pricing))

    red_flags = result["final_verdict"].red_flags
    assert red_flags.count("Property pricing is majorly drifted from local comparable averages.") == 1
    assert any("Security deposit demands are high" in f for f in red_flags)


def test_synthesis_uses_fallback_on_llm_failure(monkeypatch):
    fake_llm = RunnableLambda(lambda _: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(synthesis_mod, "get_llm", lambda temperature=0.1: fake_llm)

    pricing = PricingAnalysis(rent_amount=50000.0, deposit_amount=300000.0)
    result = synthesis_mod.synthesis_node(_state(pricing_data=pricing))

    assert result["final_verdict"].used_fallback is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. python -m pytest tests/test_synthesis.py -v`
Expected: FAIL — old code uses `parse_json_from_llm`/manual `ChatPromptTemplate`, and `used_fallback` isn't wired through this construction path yet

- [ ] **Step 3: Replace `agents/synthesis.py` contents**

```python
# agents/synthesis.py
"""
agents/synthesis.py
───────────────────
Synthesis Agent: Collates results from Vibe, Pricing, and Neighbourhood sub-agents 
to compile the final Verdict Card and custom broker questionnaire.
"""

from __future__ import annotations

import logging
from agents.config import get_llm
from agents.prompts import SYNTHESIS_PROMPT
from agents.state import AgentState, VerdictCard
from agents.fallbacks import fallback_synthesis
from agents.llm_call import call_llm_structured, LLMCallError
from agents.schemas import SynthesisResult

log = logging.getLogger(__name__)

def synthesis_node(state: AgentState) -> dict:
    log.info("[Synthesis Agent] Constructing final Verdict Card…")
    
    address_resolved = state.get("address_resolved")
    pricing_data = state.get("pricing_data")
    vibe_data = state.get("vibe_data")
    neighbourhood_data = state.get("neighbourhood_data")

    llm = get_llm(temperature=0.1)

    # Upfront Cost Calculations:
    # Bangalore standard upfront = Monthly Rent + Security Deposit + standard cleaning/brokerage (default 1 month rent)
    rent = pricing_data.rent_amount if pricing_data else 0.0
    deposit = pricing_data.deposit_amount if pricing_data else 0.0
    brokerage_and_paint = rent  # Assume 1-month rent for standard fees in Bangalore
    total_upfront_cost = rent + deposit + brokerage_and_paint

    try:
        data = call_llm_structured(
            llm,
            SYNTHESIS_PROMPT,
            {
                "address_resolved": address_resolved.model_dump() if address_resolved else {},
                "pricing_data": pricing_data.model_dump() if pricing_data else {},
                "vibe_data": vibe_data.model_dump() if vibe_data else {},
                "neighbourhood_data": neighbourhood_data.model_dump() if neighbourhood_data else {},
                "critique_section": ""
            },
            SynthesisResult
        )

        verdict = VerdictCard(
            fair_range_min=data.fair_range_min,
            fair_range_max=data.fair_range_max,
            overpriced_percentage=data.overpriced_percentage,
            total_upfront_cost=total_upfront_cost,
            red_flags=list(data.red_flags),
            neighbourhood_score=data.neighbourhood_score,
            broker_questionnaire=data.broker_questionnaire
        )

        # Proactively check for any additional price drift flag or deposit anomaly flag
        if pricing_data:
            drift_flag_text = "Property pricing is majorly drifted from local comparable averages."
            if pricing_data.price_drift_flag and drift_flag_text not in verdict.red_flags:
                verdict.red_flags.append(drift_flag_text)

            if not pricing_data.deposit_is_normal:
                deposit_flag_text = f"Security deposit demands are high ({pricing_data.deposit_multiplier}x rent)."
                if deposit_flag_text not in verdict.red_flags:
                    verdict.red_flags.append(deposit_flag_text)

        log.info("[Synthesis Agent] Final Verdict Card generated.")
        return {
            "final_verdict": verdict,
            "messages": ["[Synthesis Agent] Compiled all reports into a finalized Verdict Card with custom broker questionnaire."]
        }
        
    except LLMCallError as e:
        log.error(f"[Synthesis Agent] Error executing synthesis LLM: {e}")
        overpriced = pricing_data.overpriced_percentage if pricing_data else 0.0
        return fallback_synthesis(rent, overpriced, total_upfront_cost, str(e))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. python -m pytest tests/test_synthesis.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add agents/synthesis.py tests/test_synthesis.py
git commit -m "refactor: use structured-output LLM helper in synthesis agent; fix red-flag dedup bug"
```

---

### Task 11: Real parallel `StateGraph`

**Files:**
- Modify: `agents/graph.py:1-55` (whole file)
- Test: `tests/test_graph.py`

**Interfaces:**
- Consumes: `supervisor_node`, `pricing_node`, `vibe_check_node`, `neighbourhood_node`, `synthesis_node` (all unchanged signatures from Tasks 6-10); `langgraph.graph.StateGraph`, `END`.
- Produces: `app` — a compiled `StateGraph` exposing `.invoke(dict) -> dict`, same interface `agents/service.py::TruthTellerService.verify_listing` already expects. No change needed in `agents/service.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_graph.py
import time

from agents.graph import build_truth_teller_graph
from agents.state import AgentState


def _initial_state(listing_input: str = "test listing") -> AgentState:
    return {
        "listing_input": listing_input,
        "address_resolved": None,
        "pricing_data": None,
        "vibe_data": None,
        "neighbourhood_data": None,
        "final_verdict": None,
        "messages": [],
    }


def _slow_node(key: str, sleep_s: float):
    def node(state):
        time.sleep(sleep_s)
        return {key: f"{key}-result", "messages": [f"{key} done"]}
    return node


def test_pricing_vibe_neighbourhood_run_in_parallel(monkeypatch):
    monkeypatch.setattr(
        "agents.graph.supervisor_node",
        lambda state: {"address_resolved": None, "messages": ["supervisor done"]},
    )
    monkeypatch.setattr("agents.graph.pricing_node", _slow_node("pricing_data", 0.3))
    monkeypatch.setattr("agents.graph.vibe_check_node", _slow_node("vibe_data", 0.3))
    monkeypatch.setattr("agents.graph.neighbourhood_node", _slow_node("neighbourhood_data", 0.3))
    monkeypatch.setattr(
        "agents.graph.synthesis_node",
        lambda state: {"final_verdict": "verdict-result", "messages": ["synthesis done"]},
    )

    graph = build_truth_teller_graph()

    start = time.time()
    result = graph.invoke(_initial_state())
    elapsed = time.time() - start

    # Sequential would take >= 0.9s (3 * 0.3s); parallel should take ~0.3-0.5s.
    assert elapsed < 0.7, f"expected parallel execution, took {elapsed:.2f}s"
    assert result["pricing_data"] == "pricing_data-result"
    assert result["vibe_data"] == "vibe_data-result"
    assert result["neighbourhood_data"] == "neighbourhood_data-result"
    assert result["final_verdict"] == "verdict-result"


def test_full_graph_path_with_mocked_nodes(monkeypatch):
    monkeypatch.setattr(
        "agents.graph.supervisor_node",
        lambda state: {"address_resolved": "addr", "messages": ["supervisor done"]},
    )
    monkeypatch.setattr(
        "agents.graph.pricing_node",
        lambda state: {"pricing_data": "pricing", "messages": ["pricing done"]},
    )
    monkeypatch.setattr(
        "agents.graph.vibe_check_node",
        lambda state: {"vibe_data": "vibe", "messages": ["vibe done"]},
    )
    monkeypatch.setattr(
        "agents.graph.neighbourhood_node",
        lambda state: {"neighbourhood_data": "neigh", "messages": ["neigh done"]},
    )
    monkeypatch.setattr(
        "agents.graph.synthesis_node",
        lambda state: {"final_verdict": "verdict", "messages": ["synthesis done"]},
    )

    graph = build_truth_teller_graph()
    result = graph.invoke(_initial_state())

    assert result["address_resolved"] == "addr"
    assert result["pricing_data"] == "pricing"
    assert result["vibe_data"] == "vibe"
    assert result["neighbourhood_data"] == "neigh"
    assert result["final_verdict"] == "verdict"
    assert "supervisor done" in result["messages"]
    assert "synthesis done" in result["messages"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. python -m pytest tests/test_graph.py -v`
Expected: FAIL — current `agents/graph.py` has no `build_truth_teller_graph` importable in a way that lets `monkeypatch.setattr("agents.graph.pricing_node", ...)` affect execution meaningfully (it does today, actually, since the module-level names are called directly inside `invoke`) — but the timing assertion fails because execution is sequential (~0.9s+, not < 0.7s)

- [ ] **Step 3: Replace `agents/graph.py` contents**

```python
# agents/graph.py
"""
agents/graph.py
───────────────
Assembles the multi-agent hierarchy using LangGraph.
Handles parallel execution branches (fan-out -> fan-in):
Supervisor -> {Pricing, Vibe, Neighbourhood} (parallel) -> Synthesis.
"""

from __future__ import annotations

import logging

from langgraph.graph import StateGraph, END

from agents.state import AgentState
from agents.supervisor import supervisor_node
from agents.pricing import pricing_node
from agents.vibe import vibe_check_node
from agents.neighbourhood import neighbourhood_node
from agents.synthesis import synthesis_node

log = logging.getLogger(__name__)


def build_truth_teller_graph():
    """Builds and compiles the LangGraph StateGraph with a real
    fan-out/fan-in workflow: Supervisor resolves the address, then
    Pricing/Vibe/Neighbourhood run concurrently off that shared state,
    and Synthesis waits for all three before compiling the verdict."""
    graph = StateGraph(AgentState)

    graph.add_node("supervisor", supervisor_node)
    graph.add_node("pricing", pricing_node)
    graph.add_node("vibe", vibe_check_node)
    graph.add_node("neighbourhood", neighbourhood_node)
    graph.add_node("synthesis", synthesis_node)

    graph.set_entry_point("supervisor")

    graph.add_edge("supervisor", "pricing")
    graph.add_edge("supervisor", "vibe")
    graph.add_edge("supervisor", "neighbourhood")

    graph.add_edge("pricing", "synthesis")
    graph.add_edge("vibe", "synthesis")
    graph.add_edge("neighbourhood", "synthesis")

    graph.add_edge("synthesis", END)

    return graph.compile()


# Shared compiled graph object
app = build_truth_teller_graph()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. python -m pytest tests/test_graph.py -v`
Expected: 2 passed

- [ ] **Step 5: Manually verify `agents/service.py` still works unmodified**

`agents/service.py::TruthTellerService.verify_listing` calls `app.invoke(initial_state)` where `app` is now a compiled `StateGraph` instead of the old `SequentialGraph`. Compiled `StateGraph.invoke(dict) -> dict` has the same signature, so no code change is needed there. Confirm by reading `agents/service.py` — no edits required in this task.

- [ ] **Step 6: Commit**

```bash
git add agents/graph.py tests/test_graph.py
git commit -m "feat: rebuild agent graph on real LangGraph StateGraph with parallel fan-out/fan-in"
```

---

### Task 12: Full regression pass

**Files:** none (verification only)

- [ ] **Step 1: Run every new/modified test file together**

Run:
```bash
cd /home/deepeshmw_google_com/github/Rental-Truth-Teller
source .venv/bin/activate
PYTHONPATH=. python -m pytest \
  tests/test_cache.py \
  tests/test_schemas.py \
  tests/test_llm_call.py \
  tests/test_fallbacks.py \
  tests/test_prompts.py \
  tests/test_supervisor.py \
  tests/test_pricing.py \
  tests/test_vibe.py \
  tests/test_neighbourhood.py \
  tests/test_synthesis.py \
  tests/test_graph.py \
  -v
```

Expected: all tests pass (27 tests total across the 11 files). `tests/test_items.py` is deliberately excluded — it remains broken from before this plan and is Phase 0 scope, not touched here.

- [ ] **Step 2: Confirm `agents/utils.py::parse_json_from_llm` is now unused**

Run: `grep -rn "parse_json_from_llm" agents/ api/ rendering/`

Expected: only the definition in `agents/utils.py` itself remains — no call sites. Leave the file in place (removing dead code is Phase 0/cleanup scope, not required here), but note in the commit message that it's now unused so a future cleanup pass can delete it.

- [ ] **Step 3: Commit the verification (no-op if nothing changed)**

If Step 2's grep confirms no remaining call sites and all tests from Step 1 pass, there is nothing to commit — this task is a verification gate, not a code change. If any test fails, stop and fix the root cause in the relevant earlier task before proceeding; do not patch around it here.

---

## Out of Scope (deliberately deferred)

- `tests/test_items.py`'s broken `crawler.spiders.base_spider` import — Phase 0, explicitly skipped this round.
- Removing now-dead `agents/utils.py::parse_json_from_llm` — safe to delete after Task 12 confirms it's unused, but left as a follow-up so this plan stays focused on Phase 1's architecture goals.
- Replacing LLM-hallucinated geocoding/facility lookups with real Maps/Places APIs — that's Phase 2 (`plan.md`), which builds on this plan's `call_llm_structured`/caching plumbing but is a separate implementation plan.
- UI changes to surface `used_fallback` badges — Phase 4 (`plan.md`), depends on this plan's field existing but is a separate implementation plan.
