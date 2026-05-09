"""
config/es_client.py
────────────────────
Shared Elasticsearch client factory — compatible with elasticsearch-py 9.x.

Auth priority:
  1. API Key  — when ES_API_KEY is set (Elastic Cloud)
  2. Basic    — username + password fallback (self-hosted)

Proxy:
  On Walmart corporate network, all external HTTPS is routed through
  proxy-intlho.wal-mart.com:8080 (stored in HTTPS_PROXY env-var).
  We use RequestsHttpNode so the `requests` library handles CONNECT
  tunnelling automatically — no extra proxy config needed in code.
"""

from __future__ import annotations

import logging
import os

from elasticsearch import Elasticsearch
from elastic_transport import RequestsHttpNode

from config.settings import config

log = logging.getLogger(__name__)

_PROXY = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or ""


def build_es_client(request_timeout: int = 60) -> Elasticsearch:
    """
    Return a configured Elasticsearch 9.x client.

    Parameters
    ----------
    request_timeout : int
        Per-request timeout in seconds.
        Use 120+ for ELSER bulk-indexing operations.
    """
    # RequestsHttpNode respects HTTPS_PROXY env-var automatically.
    # Always use it on Walmart network; no harm on other networks.
    kwargs: dict = dict(
        request_timeout=request_timeout,
        retry_on_timeout=True,
        max_retries=3,
        node_class=RequestsHttpNode,   # proxy-aware HTTP backend
    )

    host_url = f"{config.ES_SCHEME}://{config.ES_HOST}:{config.ES_PORT}"

    if config.uses_api_key:
        log.info("ES → API key | %s", host_url)
        return Elasticsearch(
            host_url,
            api_key=config.ES_API_KEY,
            **kwargs,
        )
    else:
        log.info("ES → basic auth (user=%s) | %s", config.ES_USERNAME, host_url)
        return Elasticsearch(
            host_url,
            basic_auth=(config.ES_USERNAME, config.ES_PASSWORD),
            **kwargs,
        )
