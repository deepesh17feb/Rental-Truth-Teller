"""
scripts/index_mock_data.py
──────────────────────────
Reads pre-generated mock properties from output/mock_properties_20260509_102808.jsonl
and indexes them directly into Elasticsearch.

Usage:
    python scripts/index_mock_data.py
"""

import sys
import json
import logging
import hashlib
from pathlib import Path

# Allow imports from project root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import config
from config.es_client import build_es_client
from elasticsearch import helpers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("index_mock_data")

def main():
    input_file = Path(__file__).resolve().parents[1] / "output" / "mock_properties_20260509_102808.jsonl"
    if not input_file.exists():
        log.error("Input file %s not found! Run mock generation first.", input_file)
        sys.exit(1)

    log.info("Connecting to Elasticsearch...")
    es = build_es_client(request_timeout=60)
    try:
        info = es.info()
        log.info("Connected to ES index: %s (Cluster: %s)", config.ES_INDEX_PROPERTIES, info["cluster_name"])
    except Exception as e:
        log.error("Failed to connect to ES: %s", e)
        sys.exit(1)

    actions = []
    count = 0
    with open(input_file, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            doc = json.loads(line)
            # Generate unique document ID
            source = doc.get("source", "unknown")
            source_id = doc.get("source_id", "unknown")
            doc_id = hashlib.sha256(
                f"{source}::{source_id}".encode()
            ).hexdigest()
            
            actions.append({
                "_op_type": "index",
                "_index": config.ES_INDEX_PROPERTIES,
                "_id": doc_id,
                **doc
            })
            count += 1

    if not actions:
        log.warning("No properties found in %s to index.", input_file)
        return

    log.info("Ready to bulk-index %d mock documents into '%s'...", len(actions), config.ES_INDEX_PROPERTIES)
    try:
        ok, errors = helpers.bulk(
            es, actions,
            raise_on_error=False,
            raise_on_exception=False,
        )
        log.info("Bulk indexing successful! Indexed = %d, Errors = %d", ok, len(errors) if errors else 0)
        if errors:
            errors_list = list(errors) if hasattr(errors, "__iter__") and not isinstance(errors, dict) else errors
            log.error("First error encountered: %s", list(errors_list)[0] if (isinstance(errors_list, (list, tuple)) or hasattr(errors_list, "__iter__")) and len(list(errors_list)) > 0 else "unknown")
    except Exception as e:
        log.error("Failed bulk-indexing: %s", e)
        sys.exit(1)

    log.info("Indexing complete.")

if __name__ == "__main__":
    main()
