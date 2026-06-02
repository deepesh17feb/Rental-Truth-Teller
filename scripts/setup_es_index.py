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
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

from elasticsearch import Elasticsearch, exceptions as es_exc
from config.settings import config
from config.es_client import build_es_client
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

            # address: BM25 text
            "address": {
                "type": "text",
                "analyzer": "property_analyzer",
                "fields": {"raw": {"type": "keyword"}},
            },

            # ── Listing Meta ──────────────────────────────────────────────────
            # title: BM25 text
            "title": {
                "type": "text",
                "analyzer": "property_analyzer",
                "fields": {"raw": {"type": "keyword"}},
            },

            # description: BM25 text
            "description": {
                "type": "text",
                "analyzer": "property_analyzer",
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

            # ── Media ─────────────────────────────────────────────────────────
            "images": {"type": "keyword", "index": False},
        }
    },
}





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
    log.info("RentalTruth — Elasticsearch + BM25 Setup")
    log.info("  ES URL        : %s", config.es_url)
    log.info("  Index         : %s", config.ES_INDEX_PROPERTIES)
    log.info("=" * 60)

    es = build_es_client(request_timeout=60)

    # 1. Verify connectivity
    try:
        info = es.info()
        log.info("Connected → cluster=%s  version=%s",
                 info["cluster_name"], info["version"]["number"])
    except es_exc.ConnectionError as exc:
        log.error("Cannot connect to Elasticsearch: %s", exc)
        log.error("Start ES with: docker compose -f docker/docker-compose.yml up -d")
        sys.exit(1)

    # 2. Index
    create_or_update_index(es, config.ES_INDEX_PROPERTIES)

    log.info("=" * 60)
    log.info("Setup complete.")
    log.info("  BM25 Index fully configured.")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
