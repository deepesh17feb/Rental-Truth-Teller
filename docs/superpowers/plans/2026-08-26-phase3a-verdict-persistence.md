# Phase 3a: Verdict Persistence — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist every verification result to SQLite so past verdicts can be revisited, with a read-only query API (`GET /verdicts`, `GET /verdicts/{id}`), instead of every result being discarded the moment the caller is done with it.

**Architecture:** A new `agents/persistence.py` module wraps stdlib `sqlite3` with three functions (`save_verdict`, `list_verdicts`, `get_verdict`) and two response models (`VerdictSummary`, `VerdictDetail`). `agents/service.py::TruthTellerService.verify_listing` calls `save_verdict` right after a successful graph invocation — this is the single wiring point, so CLI/UI/API all get history automatically. `api/main.py` gains two new read-only endpoints. Every persistence function opens and closes its own SQLite connection (never a shared global one), since this is called from LangGraph's own parallel execution as well as FastAPI's concurrent request threads.

**Tech Stack:** stdlib `sqlite3`, `uuid`, `json`, `datetime` (no new persistence dependency). `fastapi==0.141.1`, `uvicorn==0.52.4`, `httpx==0.28.1` newly pinned in `requirements.txt` — `api/main.py` has imported and used `fastapi` since before this plan, but it was never actually pinned; this plan is the first to add automated tests exercising it (`fastapi.testclient.TestClient` needs `httpx` installed), which surfaced the gap.

**Spec:** `docs/superpowers/specs/2026-08-25-phase3-verdict-persistence-design.md`

## Global Constraints

- Do not touch `tests/test_items.py` — pre-existing broken import, Phase 0, still out of scope.
- Do not change `AgentState`'s keys or any node function's signature `def node(state: AgentState) -> dict`. This plan only touches the service/API boundary, not the graph.
- New persistence tests use pytest's `tmp_path` fixture + `monkeypatch.setattr(persistence_mod.global_config, "VERDICT_DB_PATH", ...)` to redirect each test to its own isolated SQLite file — real `sqlite3`, no mocking of the database itself, and the real `verdicts.db` is never touched by tests.
- Every persistence function opens its own `sqlite3.Connection` and closes it before returning — never a shared module-level connection object (thread-safety; see spec's rationale referencing Phase 1's cache bug).
- A persistence failure inside `TruthTellerService.verify_listing` must never fail the verification itself — log at `log.warning`, swallow the exception, still return the verification result.
- `VerdictDetail`'s sub-fields are plain `dict` (parsed JSON), not the typed `AddressResolved`/`PricingAnalysis`/etc. models from `agents/state.py` — deliberate decoupling per spec.

---

### Task 1: Config + dependency setup

**Files:**
- Modify: `config/settings.py` (add 1 field)
- Modify: `requirements.txt` (add 3 packages)

**Interfaces:**
- Produces: `config.VERDICT_DB_PATH: str` — consumed by `agents/persistence.py` in Task 2.

- [ ] **Step 1: Add `VERDICT_DB_PATH` to `config/settings.py`**

Insert this field after the OpenStreetMap section (after `OSM_REQUEST_TIMEOUT_SECONDS`), before `# ── Logging`:

```python
    # ── Persistence ───────────────────────────────────────────────────────────
    VERDICT_DB_PATH: str = Field(default="verdicts.db")
```

- [ ] **Step 2: Pin fastapi/uvicorn/httpx in `requirements.txt`**

Add a new section after "# UI & Gemini Additions" (the last section in the file):

```

# API server
fastapi==0.141.1
uvicorn==0.52.4
httpx==0.28.1
```

- [ ] **Step 3: Verify the config field loads correctly**

Run: `cd /home/deepeshmw_google_com/github/Rental-Truth-Teller/.worktrees/phase3-verdict-persistence && source .venv/bin/activate && python -c "from config.settings import config; print(config.VERDICT_DB_PATH)"`
Expected output: `verdicts.db`

- [ ] **Step 4: Install the newly pinned packages and confirm the version match**

Run: `pip install -q fastapi==0.141.1 uvicorn==0.52.4 httpx==0.28.1`
Then: `python -c "import fastapi, uvicorn, httpx; print(fastapi.__version__, uvicorn.__version__, httpx.__version__)"`
Expected: `0.141.1 0.52.4 0.28.1`

- [ ] **Step 5: Commit**

```bash
git add config/settings.py requirements.txt
git commit -m "feat: add verdict DB path config and pin fastapi/uvicorn/httpx"
```

---

### Task 2: Persistence layer

**Files:**
- Create: `agents/persistence.py`
- Test: `tests/test_persistence.py`

**Interfaces:**
- Consumes: `config.VERDICT_DB_PATH` (Task 1); `AddressResolved`, `PricingAnalysis`, `VibeAnalysis`, `NeighbourhoodAnalysis`, `VerdictCard` (from `agents/state.py`, unchanged — used only in tests to build sample data).
- Produces: `save_verdict(listing_input: str, final_state: dict) -> str`, `list_verdicts(limit: int = 20) -> list[VerdictSummary]`, `get_verdict(verdict_id: str) -> Optional[VerdictDetail]`, `VerdictSummary`, `VerdictDetail` — consumed by `agents/service.py` in Task 3 and `api/main.py` in Task 4.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_persistence.py
import agents.persistence as persistence_mod
from agents.persistence import save_verdict, list_verdicts, get_verdict
from agents.state import AddressResolved, GeoPoint, PricingAnalysis, VibeAnalysis, NeighbourhoodAnalysis, VerdictCard


def _sample_final_state(listing_input: str = "2BHK in Whitefield, rent 50000") -> dict:
    return {
        "listing_input": listing_input,
        "address_resolved": AddressResolved(raw_address="x", locality="Whitefield", geo=GeoPoint(lat=12.97, lon=77.75)),
        "pricing_data": PricingAnalysis(rent_amount=50000.0),
        "vibe_data": VibeAnalysis(listing_nlp_sentiment="Warm"),
        "neighbourhood_data": NeighbourhoodAnalysis(metro_station="Whitefield Metro"),
        "final_verdict": VerdictCard(overpriced_percentage=5.0, neighbourhood_score=7.5),
        "messages": [],
    }


def _use_temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence_mod.global_config, "VERDICT_DB_PATH", str(tmp_path / "verdicts_test.db"))


def test_save_then_get_round_trip_preserves_all_fields(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    state = _sample_final_state()

    verdict_id = save_verdict(state["listing_input"], state)
    detail = get_verdict(verdict_id)

    assert detail is not None
    assert detail.id == verdict_id
    assert detail.listing_input == state["listing_input"]
    assert detail.address_resolved["locality"] == "Whitefield"
    assert detail.pricing_data["rent_amount"] == 50000.0
    assert detail.vibe_data["listing_nlp_sentiment"] == "Warm"
    assert detail.neighbourhood_data["metro_station"] == "Whitefield Metro"
    assert detail.final_verdict["overpriced_percentage"] == 5.0


def test_save_then_list_returns_newest_first(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)

    id1 = save_verdict("first listing", _sample_final_state("first listing"))
    id2 = save_verdict("second listing", _sample_final_state("second listing"))

    summaries = list_verdicts(limit=20)

    assert [s.id for s in summaries[:2]] == [id2, id1]


def test_list_respects_limit(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)

    for i in range(5):
        save_verdict(f"listing {i}", _sample_final_state(f"listing {i}"))

    summaries = list_verdicts(limit=3)

    assert len(summaries) == 3


def test_get_verdict_returns_none_for_nonexistent_id(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)

    assert get_verdict("does-not-exist") is None


def test_none_sub_field_round_trips_as_none(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    state = _sample_final_state()
    state["final_verdict"] = None

    verdict_id = save_verdict(state["listing_input"], state)
    detail = get_verdict(verdict_id)

    assert detail.final_verdict is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. python -m pytest tests/test_persistence.py -v`
Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'agents.persistence'`

- [ ] **Step 3: Write `agents/persistence.py`**

```python
# agents/persistence.py
"""
agents/persistence.py
──────────────────────
SQLite-backed storage for verification results, so past verdicts can be
revisited instead of discarded after each request. Every function opens
and closes its own connection — no shared global connection object —
since this is called both from LangGraph's own parallel node execution
and from FastAPI's concurrent request threads.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel

from config.settings import config as global_config

log = logging.getLogger(__name__)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS verdicts (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    listing_input TEXT NOT NULL,
    locality TEXT,
    rent_amount REAL,
    overpriced_percentage REAL,
    neighbourhood_score REAL,
    address_resolved_json TEXT,
    pricing_data_json TEXT,
    vibe_data_json TEXT,
    neighbourhood_data_json TEXT,
    final_verdict_json TEXT
)
"""


class VerdictSummary(BaseModel):
    id: str
    created_at: str
    locality: str
    rent_amount: float
    overpriced_percentage: float
    neighbourhood_score: float


class VerdictDetail(BaseModel):
    id: str
    created_at: str
    listing_input: str
    address_resolved: Optional[dict] = None
    pricing_data: Optional[dict] = None
    vibe_data: Optional[dict] = None
    neighbourhood_data: Optional[dict] = None
    final_verdict: Optional[dict] = None


def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(global_config.VERDICT_DB_PATH)
    conn.execute(_CREATE_TABLE_SQL)
    conn.commit()
    return conn


def save_verdict(listing_input: str, final_state: dict) -> str:
    """Persists one verification's full result. Returns the generated verdict id."""
    verdict_id = uuid.uuid4().hex
    created_at = datetime.now(timezone.utc).isoformat()

    address_resolved = final_state.get("address_resolved")
    pricing_data = final_state.get("pricing_data")
    vibe_data = final_state.get("vibe_data")
    neighbourhood_data = final_state.get("neighbourhood_data")
    final_verdict = final_state.get("final_verdict")

    locality = address_resolved.locality if address_resolved else None
    rent_amount = pricing_data.rent_amount if pricing_data else None
    overpriced_percentage = final_verdict.overpriced_percentage if final_verdict else None
    neighbourhood_score = final_verdict.neighbourhood_score if final_verdict else None

    conn = _get_connection()
    try:
        conn.execute(
            """
            INSERT INTO verdicts (
                id, created_at, listing_input, locality, rent_amount,
                overpriced_percentage, neighbourhood_score,
                address_resolved_json, pricing_data_json, vibe_data_json,
                neighbourhood_data_json, final_verdict_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                verdict_id,
                created_at,
                listing_input,
                locality,
                rent_amount,
                overpriced_percentage,
                neighbourhood_score,
                address_resolved.model_dump_json() if address_resolved else None,
                pricing_data.model_dump_json() if pricing_data else None,
                vibe_data.model_dump_json() if vibe_data else None,
                neighbourhood_data.model_dump_json() if neighbourhood_data else None,
                final_verdict.model_dump_json() if final_verdict else None,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    log.info(f"[persistence] Saved verdict {verdict_id} for locality={locality!r}.")
    return verdict_id


def list_verdicts(limit: int = 20) -> list[VerdictSummary]:
    """Returns the most recent verdicts, newest first."""
    conn = _get_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, created_at, locality, rent_amount, overpriced_percentage, neighbourhood_score
            FROM verdicts
            ORDER BY created_at DESC, rowid DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    finally:
        conn.close()

    return [
        VerdictSummary(
            id=row[0],
            created_at=row[1],
            locality=row[2] or "",
            rent_amount=row[3] or 0.0,
            overpriced_percentage=row[4] or 0.0,
            neighbourhood_score=row[5] or 0.0,
        )
        for row in rows
    ]


def get_verdict(verdict_id: str) -> Optional[VerdictDetail]:
    """Returns the full persisted record for one verdict id, or None if not found."""
    conn = _get_connection()
    try:
        row = conn.execute(
            """
            SELECT id, created_at, listing_input, address_resolved_json,
                   pricing_data_json, vibe_data_json, neighbourhood_data_json,
                   final_verdict_json
            FROM verdicts
            WHERE id = ?
            """,
            (verdict_id,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None

    return VerdictDetail(
        id=row[0],
        created_at=row[1],
        listing_input=row[2],
        address_resolved=json.loads(row[3]) if row[3] else None,
        pricing_data=json.loads(row[4]) if row[4] else None,
        vibe_data=json.loads(row[5]) if row[5] else None,
        neighbourhood_data=json.loads(row[6]) if row[6] else None,
        final_verdict=json.loads(row[7]) if row[7] else None,
    )
```

Note: `ORDER BY created_at DESC, rowid DESC` — SQLite tables without an explicit `INTEGER PRIMARY KEY` still get an implicit `rowid` that increases with insertion order, used here as a tiebreaker in case two saves land on the same microsecond-precision timestamp.

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. python -m pytest tests/test_persistence.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add agents/persistence.py tests/test_persistence.py
git commit -m "feat: add SQLite-backed verdict persistence layer"
```

---

### Task 3: Wire persistence into `TruthTellerService`

**Files:**
- Modify: `agents/service.py` (whole file)
- Test: `tests/test_service.py` (new file — no test previously existed for this module)

**Interfaces:**
- Consumes: `save_verdict` (Task 2).
- Produces: unchanged — `TruthTellerService.verify_listing(listing_text: str) -> Dict[str, Any]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_service.py
import pytest

import agents.service as service_mod


def test_verify_listing_persists_result_on_success(monkeypatch):
    fake_final_state = {"listing_input": "2BHK in Whitefield", "final_verdict": None}
    monkeypatch.setattr(service_mod.app, "invoke", lambda state: fake_final_state)

    calls = {}

    def fake_save_verdict(listing_input, final_state):
        calls["listing_input"] = listing_input
        calls["final_state"] = final_state
        return "some-id"

    monkeypatch.setattr(service_mod, "save_verdict", fake_save_verdict)

    result = service_mod.TruthTellerService.verify_listing("2BHK in Whitefield")

    assert result == fake_final_state
    assert calls["listing_input"] == "2BHK in Whitefield"
    assert calls["final_state"] == fake_final_state


def test_verify_listing_returns_result_even_if_persistence_fails(monkeypatch):
    fake_final_state = {"listing_input": "2BHK in Whitefield", "final_verdict": None}
    monkeypatch.setattr(service_mod.app, "invoke", lambda state: fake_final_state)

    def failing_save_verdict(listing_input, final_state):
        raise RuntimeError("disk full")

    monkeypatch.setattr(service_mod, "save_verdict", failing_save_verdict)

    result = service_mod.TruthTellerService.verify_listing("2BHK in Whitefield")

    assert result == fake_final_state


def test_verify_listing_does_not_persist_on_graph_failure(monkeypatch):
    def failing_invoke(state):
        raise RuntimeError("graph exploded")

    monkeypatch.setattr(service_mod.app, "invoke", failing_invoke)

    calls = {"n": 0}

    def fake_save_verdict(listing_input, final_state):
        calls["n"] += 1
        return "id"

    monkeypatch.setattr(service_mod, "save_verdict", fake_save_verdict)

    with pytest.raises(RuntimeError):
        service_mod.TruthTellerService.verify_listing("2BHK in Whitefield")

    assert calls["n"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. python -m pytest tests/test_service.py -v`
Expected: FAIL — `agents.service` has no `save_verdict` attribute to monkeypatch yet, and the current code doesn't call it

- [ ] **Step 3: Replace `agents/service.py` contents**

```python
# agents/service.py
"""
agents/service.py
─────────────────
TruthTellerService: Orchestrates the multi-agent graph execution.
"""

from __future__ import annotations

import logging
from typing import Dict, Any, Optional

from agents.graph import app
from agents.state import AgentState
from agents.persistence import save_verdict

log = logging.getLogger(__name__)

class TruthTellerService:
    """Service to handle listing verification requests."""

    @staticmethod
    def verify_listing(listing_text: str) -> Dict[str, Any]:
        """
        Executes the multi-agent graph for a given listing.

        Args:
            listing_text: The raw text description of the rental listing.

        Returns:
            The final state of the graph including resolved data and verdict.
        """
        log.info("Starting verification for new listing...")

        initial_state: AgentState = {
            "listing_input": listing_text,
            "address_resolved": None,
            "pricing_data": None,
            "vibe_data": None,
            "neighbourhood_data": None,
            "final_verdict": None,
            "messages": []
        }

        try:
            # Invoke the compiled LangGraph
            final_state = app.invoke(initial_state)
            log.info("Verification completed successfully.")
        except Exception as e:
            log.error(f"Error during graph execution: {e}")
            raise

        try:
            save_verdict(listing_text, final_state)
        except Exception as e:
            log.warning(f"Failed to persist verdict (verification result is still returned): {e}")

        return final_state
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. python -m pytest tests/test_service.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add agents/service.py tests/test_service.py
git commit -m "feat: persist verdicts automatically on every verify_listing call"
```

---

### Task 4: Query API endpoints

**Files:**
- Modify: `api/main.py` (whole file)
- Test: `tests/test_api.py` (new file — no test previously existed for this module)

**Interfaces:**
- Consumes: `list_verdicts`, `get_verdict`, `VerdictSummary`, `VerdictDetail` (Task 2).
- Produces: `GET /verdicts` (list), `GET /verdicts/{verdict_id}` (detail, 404 if missing) — new, additive; `POST /verify` and `GET /health` unchanged.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api.py
from fastapi.testclient import TestClient

import agents.persistence as persistence_mod
from agents.state import AddressResolved, GeoPoint, VerdictCard
from api.main import app

client = TestClient(app)


def _use_temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence_mod.global_config, "VERDICT_DB_PATH", str(tmp_path / "verdicts_test.db"))


def test_list_verdicts_endpoint_returns_saved_verdicts(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)

    state = {
        "listing_input": "2BHK in Whitefield",
        "address_resolved": AddressResolved(raw_address="x", locality="Whitefield", geo=GeoPoint(lat=12.97, lon=77.75)),
        "pricing_data": None,
        "vibe_data": None,
        "neighbourhood_data": None,
        "final_verdict": VerdictCard(overpriced_percentage=5.0, neighbourhood_score=7.5),
    }
    verdict_id = persistence_mod.save_verdict(state["listing_input"], state)

    response = client.get("/verdicts")

    assert response.status_code == 200
    body = response.json()
    assert any(v["id"] == verdict_id for v in body)


def test_get_verdict_endpoint_returns_404_for_missing_id(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)

    response = client.get("/verdicts/does-not-exist")

    assert response.status_code == 404


def test_get_verdict_endpoint_returns_full_detail(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)

    state = {
        "listing_input": "2BHK in Whitefield",
        "address_resolved": AddressResolved(raw_address="x", locality="Whitefield", geo=GeoPoint(lat=12.97, lon=77.75)),
        "pricing_data": None,
        "vibe_data": None,
        "neighbourhood_data": None,
        "final_verdict": None,
    }
    verdict_id = persistence_mod.save_verdict(state["listing_input"], state)

    response = client.get(f"/verdicts/{verdict_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == verdict_id
    assert body["address_resolved"]["locality"] == "Whitefield"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. python -m pytest tests/test_api.py -v`
Expected: FAIL — `404` for `/verdicts` and `/verdicts/{id}` (routes don't exist yet, so all three tests fail on their status-code assertions)

- [ ] **Step 3: Replace `api/main.py` contents**

```python
# api/main.py
"""
api/main.py
───────────
FastAPI Entrypoint for the Rental Truth-Teller Multi-Agent System.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List

from agents.service import TruthTellerService
from agents.persistence import list_verdicts, get_verdict, VerdictSummary, VerdictDetail
from config.logging_utils import setup_logging
from config.settings import config

# Setup backend logging
setup_logging(log_file=config.BACKEND_LOG_PATH)

app = FastAPI(
    title="Rental Truth-Teller API",
    description="Multi-agent verification network for Bangalore real estate listings.",
    version="1.0.0"
)

class ListingRequest(BaseModel):
    text: str

@app.get("/health")
def health_check():
    return {"status": "healthy"}

@app.post("/verify")
def verify_listing(request: ListingRequest):
    """
    Analyzes a rental listing and returns a verified verdict card.
    Note: We use 'def' instead of 'async def' because the underlying service
    layer is synchronous and performs blocking I/O (LLM calls).
    """
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="Listing text cannot be empty.")

    try:
        result = TruthTellerService.verify_listing(request.text)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Verification failed: {str(e)}")

@app.get("/verdicts", response_model=List[VerdictSummary])
def list_verdicts_endpoint(limit: int = 20):
    """Returns the most recent persisted verdicts, newest first."""
    return list_verdicts(limit=limit)

@app.get("/verdicts/{verdict_id}", response_model=VerdictDetail)
def get_verdict_endpoint(verdict_id: str):
    """Returns the full persisted record for one verdict id."""
    detail = get_verdict(verdict_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Verdict not found.")
    return detail

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. python -m pytest tests/test_api.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add api/main.py tests/test_api.py
git commit -m "feat: add GET /verdicts and GET /verdicts/{id} query endpoints"
```

---

### Task 5: Full regression pass

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run:
```bash
cd /home/deepeshmw_google_com/github/Rental-Truth-Teller/.worktrees/phase3-verdict-persistence
source .venv/bin/activate
PYTHONPATH=. python -m pytest tests/ --ignore=tests/test_items.py -v
```

Expected: all tests pass (baseline 52 plus this plan's ~11 new = ~63 total). `tests/test_items.py` remains excluded (pre-existing, Phase 0, out of scope).

- [ ] **Step 2: Confirm the real `verdicts.db` was never touched by the test run**

Run: `ls -la /home/deepeshmw_google_com/github/Rental-Truth-Teller/.worktrees/phase3-verdict-persistence/verdicts.db 2>&1`
Expected: `No such file or directory` — every test redirected `VERDICT_DB_PATH` via `monkeypatch` to a `tmp_path`-scoped file, so no real database file should have been created in the repo root during the test run.

- [ ] **Step 3: Commit the verification (no-op if nothing changed)**

If Steps 1-2 both come back clean, there is nothing to commit — this task is a verification gate. If anything fails, stop and fix the root cause in the relevant earlier task before proceeding.

---

## Out of Scope (deliberately deferred)

- CLI `--history` flag (per your scope decision).
- UI history sidebar (Phase 4, already planned there).
- Multi-listing comparison view (Phase 3 item 2 — separate future sub-project, consumes `list_verdicts`/`get_verdict` once this lands).
- Filtering/search beyond newest-first listing with a `limit`.
- `tests/test_items.py`'s broken `crawler.spiders.base_spider` import — Phase 0, still out of scope.
