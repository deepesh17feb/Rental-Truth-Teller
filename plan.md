# Rental Truth-Teller — Enhancement Plan

Source: full codebase review (agents/, api/, rendering/, config/, crawler/, tests/) on 2026-08-19.
This is a roadmap document, not an implementation plan for a single session — each phase should get its own `writing-plans` pass before execution.

## Current State Summary

Rental Truth-Teller is a Streamlit + FastAPI app that runs a 5-step LLM pipeline (Supervisor → Pricing/Vibe/Neighbourhood → Synthesis) over a rental listing and produces a "Verdict Card." The README advertises a parallel LangGraph fan-out/fan-in architecture with grounded data lookups; the actual implementation diverges from that pitch in several important ways (see Phase 0/1/2 below).

---

## Phase 0 — Fix What's Broken (P0, do first)

The test suite and CI are currently red. Nothing else in this plan should be verified against a broken baseline.

1. **`tests/test_items.py` fails to collect.** It imports `crawler.spiders.base_spider.BangalorePropertySpider`, which does not exist — only `crawler/simple_crawler.py` and `crawler/items.py` exist, no `spiders/` package. Confirmed via `pytest`:
   ```
   ModuleNotFoundError: No module named 'crawler.spiders'
   ```
   Decide: either restore a minimal `crawler/spiders/base_spider.py` with `parse_price`/`parse_area_sqft` static methods (if that spider was meant to exist and was lost in the "remove extra files" commit), or rewrite the test against `crawler/simple_crawler.py`'s actual parsing functions. Do not leave the import dangling.

2. **Stale artifacts from deleted `agents/ralph.py`.** `agents/__pycache__/ralph.cpython-311.pyc` and `tests/__pycache__/test_ralph_loop.cpython-311-pytest-*.pyc` exist with no corresponding source files. Clean `__pycache__` directories and add them to `.gitignore` if not already covered; confirm nothing in the current codebase still references a Ralph loop concept.

3. **`USE_MOCK_LLM` is dead config.** `config/settings.py` defines `USE_MOCK_LLM: bool` but nothing in `agents/config.py::get_llm` reads it, and the Streamlit UI offers a "Mock Fallback" provider option that maps to `LLM_PROVIDER=mock`, which `get_llm` doesn't handle — it raises `ValueError: Unsupported LLM_PROVIDER: mock`. Either implement a real deterministic mock `BaseChatModel` (useful for tests/demos without API keys) and wire `USE_MOCK_LLM`/`mock` provider to it, or remove the mock option from the UI and the dead config field.

4. **Dead pylint disable/enable comment litter in `agents/synthesis.py`** (lines ~66-77) — remnants of some automated tool pass, no functional purpose. Delete.

5. **Untracked generated files in git status** — `output/*.jsonl`, `.letta/`. Confirm `output/*.jsonl` should be gitignored (keep `output/.gitkeep`) rather than committed as data.

**Exit criteria:** `PYTHONPATH=. python -m pytest tests/` passes clean; `git status` shows no stray generated files.

---

## Phase 1 — Agent Architecture Rework

The README's mermaid diagram shows a fan-out/fan-in LangGraph (Supervisor → parallel Pricing/Vibe/Neighbourhood → Synthesis). The actual `agents/graph.py` is a hand-rolled `SequentialGraph` class that calls each node function in a straight line — it doesn't import or use `langgraph.StateGraph` at all, despite `langgraph` being a pinned dependency. This is the single biggest gap between what the project claims and what it does.

1. **Real LangGraph `StateGraph`.** Rebuild `agents/graph.py` using `StateGraph(AgentState)` with actual parallel edges: Supervisor is the entry node; Pricing, Vibe, and Neighbourhood each get an edge from Supervisor and run concurrently (LangGraph handles the fan-out natively); all three converge to Synthesis. This cuts wall-clock latency roughly 2-3x since Pricing/Vibe/Neighbourhood currently run one after another and each makes at least one LLM call.

2. **Structured output instead of manual JSON scraping.** `agents/utils.py::parse_json_from_llm` does a naive `content.startswith("```json")` strip — breaks on leading whitespace, non-json-tagged code fences, or trailing commentary after the JSON block. Replace with `llm.with_structured_output(PydanticModel)` (supported by both `ChatGoogleGenerativeAI` and `ChatBedrock`) or a `PydanticOutputParser`, tied directly to the existing `agents/state.py` models (`PricingAnalysis`, `VibeAnalysis`, etc.) so parsing failures become typed validation errors instead of silent `json.loads` exceptions caught by broad `except Exception`.

3. **Retries.** `tenacity` is already a pinned dependency but unused anywhere in `agents/`. Wrap each LLM call site (or centralize in `agents/config.py::get_llm` via a retrying wrapper) with exponential backoff on transient provider errors (rate limits, timeouts) before falling through to the hardcoded fallback functions in `agents/fallbacks.py`.

4. **Cache locality-scoped LLM lookups.** Geocoding results, pricing benchmarks, and neighbourhood facility lookups are all keyed by `locality` (a small, bounded set of Bangalore areas) but get re-derived via a fresh LLM call on every single request. Add a simple TTL cache (`cachetools.TTLCache` or a small SQLite/JSON cache file) keyed by locality for `ESTIMATE_BENCHMARKS_PROMPT` and `RESOLVE_NEIGHBOURHOOD_PROMPT` results. This is a direct cost and latency win with no accuracy tradeoff once Phase 2's grounding lands (real API responses are even more cacheable than LLM guesses).

5. **Per-node error visibility.** Currently a failed sub-agent silently swaps in a fallback with no way for the caller (UI/API) to know a fallback was used versus a real result. Add a `used_fallback: bool` (or similar) field to each `*Analysis` model so the UI can flag "this section used degraded/fallback data" rather than presenting fallback numbers as if they were verified.

**Exit criteria:** graph.py uses `StateGraph`; three sub-agents provably execute concurrently (add a timing log); JSON parsing uses structured output; locality-scoped calls are cached; retries configured.

---

## Phase 2 — Ground the "Truth" in Real Data

This is the most important credibility issue: an app called "Truth-Teller" currently asks a raw LLM to invent geocoordinates and "real" nearby schools/hospitals/metro stations with no grounding, no search tool, no verification. `RESOLVE_NEIGHBOURHOOD_PROMPT` literally instructs the model to "Resolve real, actual nearby facilities" — the LLM has no way to know what's actually near a given address; it's producing plausible-sounding hallucinations. Same issue in `GEOCODE_PROMPT` asking the LLM to estimate lat/lon from locality name.

1. **Real geocoding.** Replace/augment `supervisor_node`'s LLM-based lat/lon guess with a real geocoding API call: Google Maps Geocoding API (paid, most accurate) or OpenStreetMap Nominatim (free, rate-limited, good enough for Bangalore locality-level resolution). Keep the existing `TARGET_AREAS` static-dictionary fast path for known localities; use the API (not the LLM) as the fallback for unrecognized addresses. LLM's role shrinks to extracting the *locality name/address string* from listing text — a task it's actually well-suited for — with geocoding handled by a real service.

2. **Real nearby-facility lookups.** Replace `neighbourhood_node`'s LLM-hallucinated schools/hospitals/metro/markets with Google Places API `nearbysearch` (paid) or OSM Overpass API (free) queries centered on the resolved lat/lon, filtered by type and radius. This produces real names, real distances (haversine or routing-API distance instead of LLM guesses), and is inherently more cacheable (Phase 1.4) since it's deterministic per-coordinate.

3. **Keep LLM for what it's good at.** Financial extraction (`EXTRACT_FINANCIALS_PROMPT`), vibe/NLP analysis (`VIBE_CHECK_PROMPT`), and narrative synthesis (`SYNTHESIS_PROMPT`) are legitimate LLM tasks — free text understanding, not fact lookup. No change needed there beyond Phase 1's structured-output/retry work.

4. **Surface confidence in the UI.** `AddressResolved.confidence` is computed (0.1 for no input, 0.9 for static dict match or LLM geocode, 0.4 for fallback) but never shown to the user anywhere in `rendering/ui/app.py` or the CLI. Once geocoding is grounded, show this as a badge ("Verified via Maps API" vs "Estimated" vs "Fallback — low confidence") so users know how much to trust the Verdict Card's location-derived numbers.

**Exit criteria:** geocoding and facility lookups no longer depend on LLM invention for factual claims; confidence/provenance is visible in the UI.

---

## Phase 3 — Feature Enhancements

1. **Verdict history/persistence.** Currently every verification is stateless and thrown away after the session. Persist verdicts (SQLite locally, or a dedicated Elasticsearch index alongside `bangalore_properties`) so users can revisit past verifications, and so the app itself accumulates a growing dataset of analyzed listings.

2. **Multi-listing comparison.** Given persistence, add a comparison view: run 2-3 listings side by side and rank by fair-price delta, upfront cost, red-flag count, neighbourhood score.

3. **Shareable/exportable report.** Add a "Export as PDF" or shareable-link option for the Verdict Card — useful for someone actually negotiating with a broker who wants to bring the report along.

4. **Cost & latency telemetry per agent node.** Track LLM token usage and wall-clock time per node (Supervisor/Pricing/Vibe/Neighbourhood/Synthesis) and surface it (at minimum in logs, ideally a small telemetry panel) — useful for tuning Phase 1's caching and catching regressions.

5. **Batch verification from crawler output.** `scripts/generate_mock_data.py` and the crawler pipeline already produce `output/*.jsonl` property records. Add a batch mode that runs the verification graph over a whole crawled dataset and flags outlier/suspicious listings automatically, rather than requiring one-by-one manual paste into the UI/CLI.

---

## Phase 4 — UI Overhaul

1. **Design system cleanup.** `rendering/ui/app.py` has ~50 lines of ad-hoc inline CSS (`.metric-card`, `.red-flag-box`, `.smart-question`, etc.) hardcoded into a single `st.markdown` block. Consolidate into a small set of reusable style constants/components rather than one large CSS string, and make sure it degrades gracefully in Streamlit's light theme (current styles assume dark background implicitly).

2. **Fix the map.** `pdk.Deck(..., map_style="mapbox://styles/mapbox/dark-v9")` requires a Mapbox token that isn't configured anywhere in `config/settings.py` or the `.env.example` — the pydeck map is likely rendering blank/broken today. Either wire up a `MAPBOX_API_KEY` setting or switch to a tokenless Carto/OSM basemap style.

3. **Real-time step trace, not after-the-fact log.** Currently `TruthTellerService.verify_listing` runs the whole graph synchronously and the UI only shows `final_response["messages"]` after everything completes inside a single `st.status(...)` block — there's no actual per-node progress shown live despite the README advertising a "Step-by-Step Node Visualizer." Once Phase 1 lands real parallel execution, stream per-node completion events to the UI (e.g., via `st.status` updates as each LangGraph node emits, or Streamlit's native generator/callback support) so the "real-time" claim is real.

4. **History sidebar.** Once Phase 3 adds persistence, surface past verifications in a sidebar for quick re-access.

5. **Mobile-responsive layout.** Current `st.columns([5,7])` / `[6,6]` layouts don't gracefully collapse on narrow viewports; audit and adjust for smaller screens.

6. **Light/dark theme support.** Current custom CSS hardcodes dark-theme colors; make it respect Streamlit's theme setting instead of assuming dark.

---

## Suggested Execution Order

Phase 0 → Phase 1 → Phase 2 → Phase 3 → Phase 4, since each later phase either depends on earlier ones (Phase 4's real-time trace needs Phase 1's real parallel graph; Phase 4's history sidebar needs Phase 3's persistence) or should not be built on top of a broken/unverified baseline (Phase 0). Phases 3 and 4 can interleave once Phase 2 is done, since most of Phase 3/4 items are independent of each other.

Each phase should go through its own `writing-plans` implementation-plan pass before execution — this document is the roadmap, not the step-by-step plan.
