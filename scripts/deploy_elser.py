"""
scripts/deploy_elser.py
────────────────────────
Standalone script to deploy, verify, and optionally tear down the
ELSER sparse-embedding inference endpoint used by RentalTruth.

When to run this
────────────────
  • You're using a custom ELSER_INFERENCE_ID (not the built-in endpoint).
  • You want to pre-warm ELSER before the first crawl so the model is
    already loaded when the pipeline starts bulk-indexing.
  • You want to check current endpoint / model status.

Usage
─────
    python scripts/deploy_elser.py               # deploy + verify
    python scripts/deploy_elser.py --status      # show current status only
    python scripts/deploy_elser.py --delete      # delete the custom endpoint
    python scripts/deploy_elser.py --test-query  # run a sample semantic search

Notes on the built-in endpoint
───────────────────────────────
  If ELSER_INFERENCE_ID=.elser-2-elasticsearch (the default), this script
  prints the status of the built-in endpoint but skips creation because ES
  manages that endpoint automatically.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from elasticsearch import Elasticsearch, exceptions as es_exc
from config.settings import config
from config.es_client import build_es_client

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger("deploy_elser")

INFERENCE_ID = config.ELSER_INFERENCE_ID
INDEX_NAME   = config.ES_INDEX_PROPERTIES

# Probe timeout: ELSER model download is ~250 MB and can take several minutes
PROBE_TIMEOUT_SECS = 600
PROBE_INTERVAL_SECS = 15


def get_client() -> Elasticsearch:
    return build_es_client(request_timeout=120)


# ─────────────────────────────────────────────────────────────────────────────
# Status
# ─────────────────────────────────────────────────────────────────────────────

def show_status(es: Elasticsearch) -> None:
    """Print current ELSER endpoint + ML model status."""
    log.info("=" * 55)
    log.info("ELSER Endpoint  : %s", INFERENCE_ID)
    log.info("ES URL          : %s", config.es_url)
    log.info("=" * 55)

    # Inference endpoint
    try:
        resp = es.inference.get(inference_id=INFERENCE_ID)
        endpoints = resp.get("endpoints", [resp])
        for ep in endpoints:
            log.info("Endpoint found  : %s  task=%s  service=%s",
                     ep.get("inference_id", INFERENCE_ID),
                     ep.get("task_type", "?"),
                     ep.get("service", "?"))
    except es_exc.NotFoundError:
        log.warning("Endpoint '%s' NOT found.", INFERENCE_ID)
    except Exception as exc:
        log.warning("Could not fetch endpoint info: %s", exc)

    # ML model (only relevant for custom endpoints)
    if not INFERENCE_ID.startswith("."):
        _show_ml_model_status(es)

    # Index
    try:
        if es.indices.exists(index=INDEX_NAME):
            stats = es.indices.stats(index=INDEX_NAME)
            docs  = stats["_all"]["primaries"]["docs"]["count"]
            log.info("Index '%s' — %d document(s)", INDEX_NAME, docs)
        else:
            log.warning("Index '%s' does not exist yet.", INDEX_NAME)
    except Exception as exc:
        log.warning("Could not fetch index stats: %s", exc)


def _show_ml_model_status(es: Elasticsearch) -> None:
    try:
        models = es.ml.get_trained_models(model_id=".elser_model_2")
        for m in models.get("trained_model_configs", []):
            log.info("ML model        : %s  state=%s",
                     m.get("model_id"), m.get("fully_defined", "?"))
    except es_exc.NotFoundError:
        log.info("ML model '.elser_model_2' not yet downloaded.")
    except Exception as exc:
        log.debug("ML model check skipped: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# Deploy
# ─────────────────────────────────────────────────────────────────────────────

def deploy(es: Elasticsearch) -> None:
    """Create the ELSER inference endpoint and wait for it to be ready."""

    if INFERENCE_ID.startswith("."):
        log.info(
            "Built-in endpoint '%s' — no manual deployment needed. "
            "ES downloads ELSER on first inference call.",
            INFERENCE_ID,
        )
        _warm_up(es)
        return

    # Check existence
    try:
        es.inference.get(inference_id=INFERENCE_ID)
        log.info("Endpoint '%s' already exists.", INFERENCE_ID)
        _warm_up(es)
        return
    except es_exc.NotFoundError:
        pass

    log.info("Creating ELSER inference endpoint '%s'…", INFERENCE_ID)
    es.inference.put(
        task_type="sparse_embedding",
        inference_id=INFERENCE_ID,
        body={
            "service": "elser",
            "service_settings": {
                "num_allocations": config.ELSER_NUM_ALLOCATIONS,
                "num_threads":     config.ELSER_NUM_THREADS,
                "model_id":        ".elser_model_2",
            },
        },
    )
    log.info("Endpoint created. Waiting for model to load…")
    _warm_up(es)


def _warm_up(es: Elasticsearch) -> None:
    """
    Call the inference endpoint with a test phrase.
    On first run this triggers ELSER model download; subsequent calls are fast.
    """
    log.info("Probing ELSER (may take several minutes on first run)…")
    deadline = time.time() + PROBE_TIMEOUT_SECS
    attempt  = 0

    while time.time() < deadline:
        attempt += 1
        try:
            resp = es.inference.inference(
                inference_id=INFERENCE_ID,
                task_type="sparse_embedding",
                body={"input": ["3 BHK apartment in Whitefield Bangalore near metro"]},
            )
            # Response contains sparse tokens — verify it's non-empty
            tokens = resp.get("sparse_embedding", [{}])[0]
            if tokens:
                log.info(
                    "ELSER ready after %d probe(s). "
                    "Sample token count: %d",
                    attempt, len(tokens),
                )
                return
            else:
                log.warning("Empty ELSER response on attempt %d.", attempt)
        except (es_exc.ServiceUnavailableError, es_exc.ConnectionError):
            pass
        except Exception as exc:
            log.debug("Probe attempt %d: %s", attempt, exc)

        log.info("  Not ready yet (attempt %d) — retrying in %ds…",
                 attempt, PROBE_INTERVAL_SECS)
        time.sleep(PROBE_INTERVAL_SECS)

    raise TimeoutError(
        f"ELSER endpoint '{INFERENCE_ID}' did not become ready within "
        f"{PROBE_TIMEOUT_SECS}s. Check ES ML node logs."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Delete
# ─────────────────────────────────────────────────────────────────────────────

def delete_endpoint(es: Elasticsearch) -> None:
    if INFERENCE_ID.startswith("."):
        log.error("Cannot delete built-in endpoint '%s'.", INFERENCE_ID)
        sys.exit(1)
    try:
        es.inference.delete(inference_id=INFERENCE_ID)
        log.info("Deleted inference endpoint '%s'.", INFERENCE_ID)
    except es_exc.NotFoundError:
        log.warning("Endpoint '%s' not found — nothing to delete.", INFERENCE_ID)


# ─────────────────────────────────────────────────────────────────────────────
# Test semantic query
# ─────────────────────────────────────────────────────────────────────────────

def test_query(es: Elasticsearch) -> None:
    """Run a sample semantic search against the properties index."""
    if not es.indices.exists(index=INDEX_NAME):
        log.error("Index '%s' does not exist. Run setup_es_index.py first.", INDEX_NAME)
        sys.exit(1)

    query_text = "spacious 3 bedroom flat with gym and swimming pool"
    log.info("Running semantic search: '%s'", query_text)

    resp = es.search(
        index=INDEX_NAME,
        body={
            "size": 5,
            "_source": ["title", "area", "price", "bedrooms", "transaction_type"],
            "query": {
                "semantic": {
                    "field":  "description_semantic",
                    "query":  query_text,
                }
            },
        },
    )

    hits = resp["hits"]["hits"]
    log.info("Found %d hit(s):", len(hits))
    for hit in hits:
        src = hit["_source"]
        log.info(
            "  [score=%.4f] %s | %s | %s | ₹%s | %s BHK",
            hit["_score"],
            src.get("title", "—")[:60],
            src.get("area", "?"),
            src.get("transaction_type", "?"),
            src.get("price", "?"),
            src.get("bedrooms", "?"),
        )

    if not hits:
        log.info("No results. Index some documents first with the crawler.")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deploy and manage ELSER for RentalTruth"
    )
    parser.add_argument("--status",      action="store_true", help="Show endpoint + index status")
    parser.add_argument("--delete",      action="store_true", help="Delete the custom ELSER endpoint")
    parser.add_argument("--test-query",  action="store_true", help="Run a sample semantic search")
    args = parser.parse_args()

    es = get_client()

    try:
        info = es.info()
        log.info("ES cluster: %s  version: %s",
                 info["cluster_name"], info["version"]["number"])
    except es_exc.ConnectionError as exc:
        log.error("Cannot connect to Elasticsearch: %s", exc)
        sys.exit(1)

    if args.status:
        show_status(es)
    elif args.delete:
        delete_endpoint(es)
    elif args.test_query:
        test_query(es)
    else:
        deploy(es)
        show_status(es)


if __name__ == "__main__":
    main()
