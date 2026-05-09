"""
crawler/pipelines/elasticsearch_pipeline.py
─────────────────────────────────────────────
Scrapy pipeline: PropertyItem → Elasticsearch with ELSER semantic indexing.

How ELSER works here
────────────────────
  1. `to_es_doc()` on each PropertyItem returns a document that includes
     four plain-text fields:
       title_semantic, description_semantic,
       amenities_semantic, address_semantic

  2. Those fields are typed `semantic_text` in the ES index mapping.

  3. When ES receives the document, it automatically calls the ELSER
     inference endpoint for each `semantic_text` field server-side.
     No Python-side embedding step is required.

  4. The resulting document stores both the original text and the sparse
     vector tokens, enabling semantic (sparse-vector) search in Kibana
     and via the `semantic` query DSL.

Pipeline features
─────────────────
  • Reduced batch size (10) — ELSER inference adds server-side latency
    per document, so smaller batches avoid ES timeout on bulk requests.
  • Idempotent upserts via deterministic SHA-256 doc IDs.
  • In-memory dedup within a crawl run.
  • Retry with exponential back-off (tenacity).
  • Per-spider stats on close.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import List

from elasticsearch import Elasticsearch, helpers, exceptions as es_exc
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import config
from crawler.items import PropertyItem
from crawler.spiders.base_spider import BangalorePropertySpider

log = logging.getLogger(__name__)

# ── Batch size ────────────────────────────────────────────────────────────────
# ELSER runs server-side inference for every semantic_text field in every doc.
# Smaller batches keep each bulk request under ES's default 30-second timeout.
BULK_BATCH_SIZE = 10

# ── Request timeout ───────────────────────────────────────────────────────────
# Allow extra time for ELSER inference on each batch.
ES_REQUEST_TIMEOUT = 120   # seconds


class ElasticsearchPipeline:
    """Scrapy item pipeline: PropertyItem → Elasticsearch (ELSER-enabled)."""

    def __init__(self):
        self._client: Elasticsearch | None = None
        self._buffer: List[dict] = []
        self._stats: dict = defaultdict(int)
        self._seen_ids: set[str] = set()    # In-memory dedup within a crawl run

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    @classmethod
    def from_crawler(cls, crawler):
        return cls()

    def open_spider(self, spider):
        log.info("[ELSER Pipeline] Connecting to Elasticsearch at %s…", config.es_url)
        log.info("[ELSER Pipeline] ELSER inference endpoint: %s", config.ELSER_INFERENCE_ID)

        self._client = Elasticsearch(
            hosts=[{
                "host": config.ES_HOST,
                "port": config.ES_PORT,
                "scheme": config.ES_SCHEME,
            }],
            basic_auth=config.es_auth,
            request_timeout=ES_REQUEST_TIMEOUT,
            retry_on_timeout=True,
            max_retries=3,
        )
        self._ensure_index_exists()

    def close_spider(self, spider):
        if self._buffer:
            self._flush()

        log.info(
            "[ELSER Pipeline] Spider '%s' finished. "
            "indexed=%d  skipped_dupe=%d  errors=%d",
            spider.name,
            self._stats["indexed"],
            self._stats["skipped_dupe"],
            self._stats["errors"],
        )

    # ── Item processing ───────────────────────────────────────────────────────

    def process_item(self, item, spider):
        if not isinstance(item, PropertyItem):
            return item

        doc_id = BangalorePropertySpider.make_doc_id(item.source, item.source_id)

        # In-run dedup
        if doc_id in self._seen_ids:
            self._stats["skipped_dupe"] += 1
            return item
        self._seen_ids.add(doc_id)

        # Build ES bulk action.
        # Using _op_type=index (not update) because:
        #   • semantic_text fields cannot be partially updated — the whole
        #     document must be re-indexed so ES re-runs ELSER inference.
        #   • We achieve idempotency via the deterministic _id.
        doc = item.to_es_doc()
        action = {
            "_op_type": "index",          # full-document replace (idempotent via _id)
            "_index": config.ES_INDEX_PROPERTIES,
            "_id": doc_id,
            **doc,
        }
        self._buffer.append(action)

        if len(self._buffer) >= BULK_BATCH_SIZE:
            self._flush()

        return item

    # ── Bulk flush ────────────────────────────────────────────────────────────

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=4, max=30),
        reraise=True,
    )
    def _flush(self) -> None:
        if not self._buffer:
            return

        batch = self._buffer.copy()
        self._buffer.clear()

        log.info(
            "[ELSER Pipeline] Flushing %d docs → ES will run ELSER inference server-side…",
            len(batch),
        )

        try:
            success, errors = helpers.bulk(
                self._client,
                batch,
                raise_on_error=False,
                raise_on_exception=False,
                chunk_size=BULK_BATCH_SIZE,
                # Give ES extra time per chunk for ELSER inference
                request_timeout=ES_REQUEST_TIMEOUT,
            )
            self._stats["indexed"] += success

            if errors:
                self._stats["errors"] += len(errors)
                for err in errors[:5]:
                    # Surface the actual ES error reason if available
                    reason = (
                        err.get("index", {})
                        .get("error", {})
                        .get("reason", str(err))
                    )
                    log.error("[ELSER Pipeline] Bulk error: %s", reason)

            log.info(
                "[ELSER Pipeline] Batch done — success=%d, errors=%d",
                success,
                len(errors) if errors else 0,
            )

        except es_exc.ConnectionError as exc:
            log.error("[ELSER Pipeline] Connection lost during flush: %s", exc)
            # Restore buffer so tenacity retry picks them up
            self._buffer = batch + self._buffer
            raise

        except es_exc.RequestError as exc:
            # Malformed document — log and discard (don't retry)
            log.error("[ELSER Pipeline] Request error (bad doc?): %s", exc)
            self._stats["errors"] += len(batch)

    # ── Safety check ─────────────────────────────────────────────────────────

    def _ensure_index_exists(self) -> None:
        """Warn if the index (with ELSER mapping) hasn't been created yet."""
        try:
            exists = self._client.indices.exists(index=config.ES_INDEX_PROPERTIES)
            if not exists:
                log.warning(
                    "[ELSER Pipeline] Index '%s' not found! "
                    "Run: python scripts/setup_es_index.py",
                    config.ES_INDEX_PROPERTIES,
                )
            else:
                log.info(
                    "[ELSER Pipeline] Index '%s' verified.",
                    config.ES_INDEX_PROPERTIES,
                )
        except es_exc.ConnectionError as exc:
            log.error("[ELSER Pipeline] Cannot verify index: %s", exc)
