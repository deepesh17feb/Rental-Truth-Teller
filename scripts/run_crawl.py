"""
scripts/run_crawl.py
─────────────────────
Standalone crawler runner — no Scrapy needed.

What it does:
  1. Crawls MagicBricks + 99acres for Whitefield & Koramangala (Bangalore).
  2. Writes every item to  output/properties_<timestamp>.jsonl  immediately
     so you can see results in real-time.
  3. Pushes to Elasticsearch / ELSER when ES_API_KEY is valid.
     Skips ES and logs a warning when the key is missing/invalid.

Usage:
    python3 scripts/run_crawl.py                  # crawl all, write JSONL + ES
    python3 scripts/run_crawl.py --no-es          # JSONL only (skip ES)
    python3 scripts/run_crawl.py --source mb      # MagicBricks only
    python3 scripts/run_crawl.py --source 99      # 99acres only
    python3 scripts/run_crawl.py --area whitefield --tx rent
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# ── Project root on sys.path ──────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import config
from config.areas import TARGET_AREAS
from crawler.items import PropertyItem
from crawler.simple_crawler import BangaloreCrawler, MagicBricksCrawler, NinetyAcresCrawler, _build_session

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("run_crawl")

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"


# ─────────────────────────────────────────────────────────────────────────────
# JSONL writer (always-on, real-time)
# ─────────────────────────────────────────────────────────────────────────────

class JsonlWriter:
    def __init__(self, filepath: Path):
        self.filepath = filepath
        self.count = 0
        filepath.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(filepath, "w", encoding="utf-8")
        log.info("Writing JSONL → %s", filepath)

    def write(self, item: PropertyItem) -> None:
        self._fh.write(json.dumps(item.to_es_doc(), ensure_ascii=False) + "\n")
        self._fh.flush()
        self.count += 1

    def close(self) -> None:
        self._fh.close()
        log.info("JSONL closed — %d records written to %s", self.count, self.filepath)


# ─────────────────────────────────────────────────────────────────────────────
# Elasticsearch writer (optional)
# ─────────────────────────────────────────────────────────────────────────────

class ESWriter:
    BATCH = 10   # smaller batches for ELSER inference latency

    def __init__(self):
        self._client   = None
        self._buffer   = []
        self._stats    = defaultdict(int)
        self._enabled  = False
        self._setup()

    def _setup(self) -> None:
        if not config.ES_API_KEY and not config.ES_PASSWORD:
            log.warning("ES skipped — no credentials in .env")
            return
        try:
            from config.es_client import build_es_client
            from elasticsearch import exceptions as es_exc
            client = build_es_client(request_timeout=120)
            client.info()                  # connectivity check
            self._client  = client
            self._enabled = True
            log.info("ES connected → %s", config.es_url)
            log.info("ELSER endpoint → %s", config.ELSER_INFERENCE_ID)
        except Exception as exc:
            log.warning("ES unavailable (%s) — will write JSONL only.", exc)

    def write(self, item: PropertyItem) -> None:
        if not self._enabled:
            return
        import hashlib
        doc_id = hashlib.sha256(
            f"{item.source}::{item.source_id}".encode()
        ).hexdigest()
        self._buffer.append((doc_id, item.to_es_doc()))
        if len(self._buffer) >= self.BATCH:
            self._flush()

    def flush(self) -> None:
        if self._buffer:
            self._flush()

    def _flush(self) -> None:
        if not self._enabled or not self._buffer:
            return
        from elasticsearch import helpers, exceptions as es_exc

        actions = [
            {
                "_op_type": "index",
                "_index":   config.ES_INDEX_PROPERTIES,
                "_id":      doc_id,
                **doc,
            }
            for doc_id, doc in self._buffer
        ]
        self._buffer.clear()
        try:
            ok, errors = helpers.bulk(
                self._client, actions,
                raise_on_error=False,
                raise_on_exception=False,
            )
            self._stats["indexed"] += ok
            if errors:
                self._stats["errors"] += len(errors)
                errors = list(errors) if hasattr(errors, "__iter__") and not isinstance(errors, dict) else errors
                err = list(errors)[0] if (isinstance(errors, (list, tuple)) or hasattr(errors, "__iter__")) and list(errors) else {}
                reason = err.get("index", {}).get("error", {}).get("reason", str(err)) if isinstance(err, dict) else str(err)
                log.error("ES bulk error (first): %s", reason)
            log.info("ES flushed → +%d indexed  (total=%d  errors=%d)",
                     ok, self._stats["indexed"], self._stats["errors"])
        except es_exc.ConnectionError as exc:
            log.error("ES connection lost during flush: %s", exc)

    @property
    def enabled(self) -> bool:
        return self._enabled


# ─────────────────────────────────────────────────────────────────────────────
# Main runner
# ─────────────────────────────────────────────────────────────────────────────

def run(args: argparse.Namespace) -> None:
    ts        = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    jsonl_out = OUTPUT_DIR / f"properties_{ts}.jsonl"

    jw = JsonlWriter(jsonl_out)
    ew = ESWriter() if not args.no_es else None

    if ew and not ew.enabled:
        log.warning("Running in JSONL-only mode (ES unavailable).")

    stats: dict = defaultdict(int)
    session   = _build_session()
    crawlers  = {
        "mb": MagicBricksCrawler(session),
        "99": NinetyAcresCrawler(session),
    }

    # Resolve which crawlers to run
    sources = (
        ["mb", "99"] if args.source == "all"
        else [args.source]
    )

    # Resolve which areas to run
    areas = TARGET_AREAS
    if args.area:
        key = args.area.lower().replace(" ", "")
        areas = {k: v for k, v in TARGET_AREAS.items() if key in k}
        if not areas:
            log.error("Unknown area '%s'. Valid: %s", args.area, list(TARGET_AREAS))
            sys.exit(1)

    # Resolve transaction types
    tx_types = (
        [args.tx] if args.tx
        else (["rent", "sale"] if config.TRANSACTION_TYPE == "both"
              else [config.TRANSACTION_TYPE])
    )

    log.info("=" * 60)
    log.info("RentalTruth Crawler Starting")
    log.info("  Areas   : %s", [a.name for a in areas.values()])
    log.info("  Sources : %s", sources)
    log.info("  Tx types: %s", tx_types)
    log.info("  Output  : %s", jsonl_out)
    log.info("  ES push : %s", "YES" if (ew and ew.enabled) else "NO (JSONL only)")
    log.info("=" * 60)

    start_time = time.time()

    try:
        for area_key, area in areas.items():
            for src in sources:
                crawler = crawlers[src]
                source_name = "MagicBricks" if src == "mb" else "99acres"

                for tx in tx_types:
                    log.info("▶ %s | %s | %s", source_name, area.name, tx)
                    page_count = 0
                    for item in crawler.crawl(area, tx):
                        jw.write(item)
                        if ew:
                            ew.write(item)
                        stats["total"] += 1
                        stats[f"{src}_{tx}"] += 1
                        page_count += 1

                        # Live progress every 10 items
                        if stats["total"] % 10 == 0:
                            log.info(
                                "  ↳ %d items so far | latest: [%s] %s — ₹%s",
                                stats["total"],
                                item.area,
                                (item.title or "no title")[:50],
                                int(item.price) if item.price else "?",
                            )

                    log.info("  ✓ %s | %s | %s → %d items",
                             source_name, area.name, tx, page_count)

    except KeyboardInterrupt:
        log.info("Interrupted by user.")

    finally:
        # Final ES flush
        if ew:
            ew.flush()
        jw.close()

    elapsed = time.time() - start_time
    log.info("=" * 60)
    log.info("Crawl complete in %.1fs", elapsed)
    log.info("  Total items   : %d", stats["total"])
    for k, v in sorted(stats.items()):
        if k != "total":
            log.info("  %-20s: %d", k, v)
    log.info("  JSONL file    : %s", jsonl_out)
    if ew and ew.enabled:
        log.info("  ES indexed    : %d", ew._stats["indexed"])
    log.info("=" * 60)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="RentalTruth — Bangalore property crawler"
    )
    parser.add_argument(
        "--source", choices=["all", "mb", "99"], default="all",
        help="Source to crawl: all | mb (MagicBricks) | 99 (99acres)"
    )
    parser.add_argument(
        "--area", default=None,
        help="Specific area to crawl (default: all configured areas)"
    )
    parser.add_argument(
        "--tx", choices=["rent", "sale"], default=None,
        help="Transaction type (default: both from .env)"
    )
    parser.add_argument(
        "--no-es", action="store_true",
        help="Disable Elasticsearch indexing — write JSONL only"
    )
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
