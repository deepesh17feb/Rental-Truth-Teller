"""
scripts/setup_es_index.py
──────────────────────────
Creates the Elasticsearch index + ELSER inference endpoint for
Bangalore property documents.

What this does:
  1. Connects to ES and checks the cluster.
  2. Creates (or verifies) the ELSER sparse-embedding inference endpoint.
  3. Waits for ELSER to be ready (first run downloads the model — ~5 min).
  4. Creates / updates the index with both BM25 text fields and
     semantic_text fields backed by ELSER.

Run once before the first crawl:
    python scripts/setup_es_index.py

Re-run any time you change the mapping (new fields are added safely).
"""

from __future__ import annotations

import sys
import time
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from elasticsearch import Elasticsearch, exceptions as es_exc
from config.settings import config

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger("setup_es_index")

# ─────────────────────────────────────────────────────────────────────────────
# ELSER inference endpoint
# ─────────────────────────────────────────────────────────────────────────────
# We use the built-in ".elser-2-elasticsearch" endpoint (ES 8.13+) by default.
# It downloads and deploys ELSER v2 automatically on first use.
# To use a custom endpoint, change ELSER_INFERENCE_ID in .env and run
# scripts/deploy_elser.py first.
ELSER_INFERENCE_ID = config.ELSER_INFERENCE_ID

# ─────────────────────────────────────────────────────────────────────────────
# Index mapping
# ─────────────────────────────────────────────────────────────────────────────
#
# Strategy — dual-field approach for hybrid search:
#   • text fields      → BM25 keyword/lexical search + filtering
#   • semantic_text    → ELSER sparse-embedding semantic search
#
# Semantic fields (type: semantic_text):
#   title_semantic       ← populated from `title`
#   description_semantic ← populated from `description`
#   amenities_semantic   ← populated from amenities list joined as text
#   address_semantic     ← populated from `address`
#
# ES calls the ELSER inference endpoint automatically at index time.
# The client just sends the plain text; ES handles the embedding.
# ─────────────────────────────────────────────────────────────────────────────

INDEX_BODY = {
    "settings": {
        "number_of_shards": config.ES_INDEX_SHARDS,
        "number_of_replicas": config.ES_INDEX_REPLICA,
        "analysis": {
            "analyzer": {
                "property_analyzer": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": ["lowercase", "asciifolding", "stop"],
                }
            }
        },
    },
    "mappings": {
        "properties": {
            # ── Identity ─────────────────────────────────────────────────────
            "source":     {"type": "keyword"},
            "source_id":  {"type": "keyword"},
            "url":        {"type": "keyword", "index": False},
            "crawled_at": {"type": "date"},

            # ── Location ──────────────────────────────────────────────────────
            "area":    {"type": "keyword"},
            "city":    {"type": "keyword"},
            "state":   {"type": "keyword"},
            "pincode": {"type": "keyword"},
            "geo":     {"type": "geo_point"},

            # address: BM25 text + ELSER semantic
            "address": {
                "type": "text",
                "analyzer": "property_analyzer",
                "fields": {"raw": {"type": "keyword"}},
            },
            "address_semantic": {
                "type": "semantic_text",
                "inference_id": ELSER_INFERENCE_ID,
            },

            # ── Listing Meta ──────────────────────────────────────────────────
            # title: BM25 text + ELSER semantic
            "title": {
                "type": "text",
                "analyzer": "property_analyzer",
                "fields": {"raw": {"type": "keyword"}},
            },
            "title_semantic": {
                "type": "semantic_text",
                "inference_id": ELSER_INFERENCE_ID,
            },

            # description: BM25 text + ELSER semantic
            "description": {
                "type": "text",
                "analyzer": "property_analyzer",
            },
            "description_semantic": {
                "type": "semantic_text",
                "inference_id": ELSER_INFERENCE_ID,
            },

            "transaction_type": {"type": "keyword"},   # rent | sale
            "property_type":    {"type": "keyword"},   # apartment | villa ...
            "posted_by":        {"type": "keyword"},   # owner | agent | builder
            "posted_date":      {
                "type": "date",
                "format": "yyyy-MM-dd||strict_date_optional_time",
            },

            # ── Specs ─────────────────────────────────────────────────────────
            "bedrooms":         {"type": "integer"},
            "bathrooms":        {"type": "integer"},
            "area_sqft":        {"type": "float"},
            "floor":            {"type": "integer"},
            "total_floors":     {"type": "integer"},
            "furnishing":       {"type": "keyword"},
            "facing":           {"type": "keyword"},
            "age_of_property":  {"type": "keyword"},

            # ── Financials ────────────────────────────────────────────────────
            "price":            {"type": "long"},
            "price_unit":       {"type": "keyword"},
            "price_per_sqft":   {"type": "float"},
            "deposit":          {"type": "long"},
            "maintenance":      {"type": "float"},

            # ── Amenities ─────────────────────────────────────────────────────
            # amenities: keyword list for exact filters
            "amenities": {"type": "keyword"},
            # amenities_semantic: ELSER-encoded joined string for semantic search
            # e.g. "swimming pool gym parking clubhouse"
            "amenities_semantic": {
                "type": "semantic_text",
                "inference_id": ELSER_INFERENCE_ID,
            },

            # ── Media ─────────────────────────────────────────────────────────
            "images": {"type": "keyword", "index": False},
        }
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_es_client() -> Elasticsearch:
    return Elasticsearch(
        hosts=[{
            "host": config.ES_HOST,
            "port": config.ES_PORT,
            "scheme": config.ES_SCHEME,
        }],
        basic_auth=config.es_auth,
        request_timeout=60,
        retry_on_timeout=True,
        max_retries=3,
    )


def ensure_elser_inference_endpoint(es: Elasticsearch) -> None:
    """
    Create the ELSER sparse-embedding inference endpoint if it doesn't exist.

    For the built-in '.elser-2-elasticsearch' endpoint (ES 8.13+):
      - ES downloads and deploys ELSER v2 automatically on first inference.
      - No explicit model deployment step is needed.

    For a custom endpoint (e.g. 'elser-bangalore-properties'):
      - We create it here with explicit resource settings.
      - First inference call will trigger model download (~250 MB).
    """
    inference_id = ELSER_INFERENCE_ID

    # Built-in endpoint — always exists, nothing to create
    if inference_id.startswith(".elser-2"):
        log.info("Using built-in ELSER endpoint '%s' — no setup needed.", inference_id)
        return

    # Check if custom endpoint already exists
    try:
        existing = es.inference.get(inference_id=inference_id)
        log.info("ELSER inference endpoint '%s' already exists.", inference_id)
        return
    except es_exc.NotFoundError:
        pass
    except Exception as exc:
        log.warning("Could not check inference endpoint: %s", exc)

    # Create custom ELSER endpoint
    log.info("Creating ELSER inference endpoint '%s'…", inference_id)
    es.inference.put(
        task_type="sparse_embedding",
        inference_id=inference_id,
        body={
            "service": "elser",
            "service_settings": {
                "num_allocations": config.ELSER_NUM_ALLOCATIONS,
                "num_threads": config.ELSER_NUM_THREADS,
                "model_id": ".elser_model_2",
            },
        },
    )
    log.info("ELSER inference endpoint '%s' created.", inference_id)
    _wait_for_elser_ready(es, inference_id)


def _wait_for_elser_ready(es: Elasticsearch, inference_id: str, timeout: int = 600) -> None:
    """
    Block until ELSER responds to a test inference.
    The first call triggers model download (~250 MB); allow up to 10 minutes.
    """
    log.info("Waiting for ELSER to be ready (model may need to download)…")
    deadline = time.time() + timeout
    attempt = 0

    while time.time() < deadline:
        attempt += 1
        try:
            es.inference.inference(
                inference_id=inference_id,
                task_type="sparse_embedding",
                body={"input": ["test"]},
            )
            log.info("ELSER is ready after %d attempt(s).", attempt)
            return
        except es_exc.ServiceUnavailableError:
            log.info("  ELSER not ready yet (attempt %d) — waiting 15s…", attempt)
            time.sleep(15)
        except Exception as exc:
            log.warning("  ELSER probe error (attempt %d): %s", attempt, exc)
            time.sleep(15)

    raise TimeoutError(
        f"ELSER inference endpoint '{inference_id}' did not become ready "
        f"within {timeout}s. Check ES ML node logs."
    )


def create_or_update_index(es: Elasticsearch, index_name: str) -> None:
    """Idempotently create or update the index."""
    if es.indices.exists(index=index_name):
        log.info("Index '%s' exists — adding any new mapping fields.", index_name)
        # put_mapping only ADDS fields; it never removes or changes existing ones
        es.indices.put_mapping(
            index=index_name,
            body=INDEX_BODY["mappings"],
        )
        log.info("Mapping refreshed.")
    else:
        log.info("Creating index '%s'…", index_name)
        es.indices.create(index=index_name, body=INDEX_BODY)
        log.info("Index '%s' created.", index_name)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    log.info("=" * 60)
    log.info("RentalTruth — Elasticsearch + ELSER Setup")
    log.info("  ES URL        : %s", config.es_url)
    log.info("  Index         : %s", config.ES_INDEX_PROPERTIES)
    log.info("  ELSER endpoint: %s", ELSER_INFERENCE_ID)
    log.info("=" * 60)

    es = get_es_client()

    # 1. Verify connectivity
    try:
        info = es.info()
        log.info("Connected → cluster=%s  version=%s",
                 info["cluster_name"], info["version"]["number"])
    except es_exc.ConnectionError as exc:
        log.error("Cannot connect to Elasticsearch: %s", exc)
        log.error("Start ES with: docker compose -f docker/docker-compose.yml up -d")
        sys.exit(1)

    # 2. ELSER inference endpoint
    ensure_elser_inference_endpoint(es)

    # 3. Index
    create_or_update_index(es, config.ES_INDEX_PROPERTIES)

    log.info("=" * 60)
    log.info("Setup complete.")
    log.info("  Semantic search fields: title_semantic, description_semantic,")
    log.info("                          amenities_semantic, address_semantic")
    log.info("  Inference endpoint    : %s", ELSER_INFERENCE_ID)
    log.info("=" * 60)


if __name__ == "__main__":
    main()
