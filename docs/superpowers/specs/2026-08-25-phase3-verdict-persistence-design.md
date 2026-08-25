# Phase 3a: Verdict Persistence — Design

**Status:** Approved by user 2026-08-25, pending spec self-review.

**Scope note:** This is the first of five independent sub-projects under `plan.md`'s Phase 3 ("Feature Enhancements"). Persistence is foundational — Phase 3 item 2 (multi-listing comparison) and item 5 (batch verification) both build on it. Items 3 (export) and 4 (telemetry) are unrelated and get their own future spec/plan cycles.

**Branch note:** Branches from `phase2-real-data-grounding` (PR #5, not yet merged to `local-bm25`), since that PR's code (not just its plan doc, which is already on `local-bm25`) is where the current `config/settings.py`, `agents/service.py`, etc. actually live.

## Problem

Every verification is stateless today — `TruthTellerService.verify_listing` runs the graph and returns the result, which is discarded the moment the caller (CLI/UI/API) is done with it. There's no way to revisit a past verdict, no dataset accumulating for future features (comparison, batch analysis), and no persistence layer to build those on.

## Decisions

- **Storage: SQLite**, via Python's stdlib `sqlite3` — no new dependency, works offline, consistent with this project's demonstrated preference for free/local/zero-setup infrastructure (Phase 2 chose OSM over paid Maps APIs for the same reason).
- **Scope: backend-only.** Storage layer + automatic persistence on every `verify_listing` call + a read-only query API. No CLI flag, no UI changes — the UI history sidebar is already explicitly scoped to Phase 4 in `plan.md`.
- **Wiring point:** inside `TruthTellerService.verify_listing`, so CLI, Streamlit UI, and the FastAPI `/verify` endpoint all get history "for free" with no per-caller changes.
- **Failure handling:** best-effort. A save failure is logged and does not fail the verification itself — consistent with the app's existing fallback-everywhere philosophy (every agent node already degrades gracefully rather than crashing the whole run).
- **Connection-per-operation**, not one shared global connection — Phase 1's final review caught a thread-safety bug from a shared mutable cache object being accessed by LangGraph's concurrent branches; FastAPI can similarly call this module from concurrent request threads (`api/main.py`'s `/verify` handler is `def`, not `async def`, so each request runs on its own threadpool worker). Opening a fresh `sqlite3.connect(...)` per call sidesteps that whole class of bug — SQLite's own file-level locking handles the rest at this app's volume.

## Architecture

### `agents/persistence.py` (new)

```python
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
    address_resolved: Optional[dict]
    pricing_data: Optional[dict]
    vibe_data: Optional[dict]
    neighbourhood_data: Optional[dict]
    final_verdict: Optional[dict]

def save_verdict(listing_input: str, final_state: dict) -> str:
    """Persists one verification's full result. Returns the generated verdict id."""

def list_verdicts(limit: int = 20) -> list[VerdictSummary]:
    """Returns the most recent verdicts, newest first."""

def get_verdict(verdict_id: str) -> Optional[VerdictDetail]:
    """Returns the full persisted record for one verdict id, or None if not found."""
```

`VerdictDetail`'s sub-fields are `dict`, not the typed `AddressResolved`/`PricingAnalysis`/etc. models from `agents/state.py` — deliberately. Round-tripping through those types isn't needed for read-only display, and decoupling from them means this module doesn't need four extra imports that would need updating every time `agents/state.py`'s models evolve (e.g. Phase 1's `used_fallback` field, Phase 2's coordinate changes — this module doesn't care about either).

**Schema** (single table, one row per verification):

```sql
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
```

The five `*_json` columns hold `model_dump_json()` output from the corresponding `AgentState` sub-model (or SQL `NULL` if that sub-agent's result was `None` — e.g. `final_verdict` is `None` on a failed synthesis before its own fallback kicks in, though in practice `synthesis_node`'s fallback always populates it; still worth handling `None` defensively rather than assuming). `locality`/`rent_amount`/`overpriced_percentage`/`neighbourhood_score` are denormalized from `pricing_data`/`neighbourhood_data`/`final_verdict` at write time, purely so `list_verdicts` doesn't need to parse JSON for every row just to build a summary line.

`id`: `uuid.uuid4().hex` (stdlib). `created_at`: `datetime.now(timezone.utc).isoformat()` (stdlib).

**Connection helper:**

```python
def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(global_config.VERDICT_DB_PATH)
    conn.execute(_CREATE_TABLE_SQL)
    conn.commit()
    return conn
```

Called fresh at the top of every public function; each function does its work inside a `try/finally` that closes the connection. `CREATE TABLE IF NOT EXISTS` on every open is cheap at this app's volume and means there's no separate migration/init step to forget to run.

### `config/settings.py`

```python
VERDICT_DB_PATH: str = Field(default="verdicts.db")
```

Inserted after the OpenStreetMap section (Phase 2), before Logging — matches the existing `cli.log`/`ui.log`/`backend.log` convention of a root-level file with a working default, no `.env` changes required to run.

### `agents/service.py`

`TruthTellerService.verify_listing` calls `save_verdict(listing_text, final_state)` right after `app.invoke(initial_state)` succeeds, wrapped so a persistence failure is logged (`log.warning`, not `log.error` — it's degraded-but-fine, not degraded-and-concerning like an agent fallback) and does not raise. The method's return value and signature are otherwise unchanged.

### `api/main.py`

Two new read-only endpoints:

```python
@app.get("/verdicts")
def list_verdicts_endpoint(limit: int = 20) -> list[VerdictSummary]: ...

@app.get("/verdicts/{verdict_id}")
def get_verdict_endpoint(verdict_id: str) -> VerdictDetail:
    # 404 if not found
```

### Unchanged files

`agents/graph.py`, all five node modules, `agents/state.py`, `agents/cache.py`, `agents/llm_call.py`, `agents/geocoding.py`, `agents/facilities.py`, `rendering/*` — no changes. `AgentState`'s shape and every node's interface are untouched; this is purely additive at the service-layer boundary.

## Testing

- `tests/test_persistence.py`: use `tmp_path` (pytest's built-in temp-directory fixture) for a real, isolated SQLite file per test — no mocking of `sqlite3` itself, genuine read/write round-trips. Cover: save-then-get round-trip preserves all fields, save-then-list returns newest-first, list respects `limit`, get on a nonexistent id returns `None`, a `None` sub-field (e.g. `final_verdict=None`) round-trips as `None` not a JSON-encoded null string.
- `tests/test_service.py` (new — no existing test file for `agents/service.py`): verify `verify_listing` calls `save_verdict` with the right arguments on success, and verify a `save_verdict` exception is caught/logged without propagating (the verification's own result must still be returned).
- API endpoint tests added to a new `tests/test_api.py` using FastAPI's `TestClient` (already available via the `fastapi` dependency — no new package needed): `GET /verdicts` returns a list, `GET /verdicts/{id}` returns 200 with the right shape for an existing id and 404 for a missing one.

## Out of scope (deliberately deferred)

- CLI `--history` flag (explicitly deferred this round, per your scope decision).
- UI history sidebar (Phase 4, already planned there).
- Multi-listing comparison view (Phase 3 item 2 — a separate sub-project that will consume `list_verdicts`/`get_verdict` once this lands).
- Any filtering/search beyond newest-first listing with a limit.
- Migrating existing crawled `output/*.jsonl` data or the Elasticsearch `bangalore_properties` index into this table — this table is for verification *results*, not source listings.
