"""
config/es_client.py
────────────────────
Shared Elasticsearch client factory.

Auth priority:
  1. API Key  — when ES_API_KEY is set (Elastic Cloud default)
  2. Basic    — username + password fallback (self-hosted)

Proxy:
  Walmart corporate network routes external HTTPS through
  proxy-intlho.wal-mart.com:8080.  The default urllib3 backend
  tries direct DNS resolution first (which fails on-prem).
  We use elastic_transport.RequestsHttpNode instead — it delegates
  to the `requests` library, which honours the HTTPS_PROXY /
  HTTP_PROXY environment variables and correctly tunnels via CONNECT.
"""

from __future__ import annotations

import logging
import os

from elasticsearch import Elasticsearch
from elastic_transport import RequestsHttpNode

from config.settings import config

log = logging.getLogger(__name__)

# Detect whether a corporate proxy is active
_PROXY = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or ""


def build_es_client(request_timeout: int = 60) -> Elasticsearch:
    """
    Return a configured Elasticsearch client.

    Parameters
    ----------
    request_timeout : int
        Per-request timeout in seconds.
        Pass 120+ for ELSER bulk-indexing operations.
    """
    kwargs: dict = dict(
        request_timeout=request_timeout,
        retry_on_timeout=True,
        max_retries=3,
    )

    # Use RequestsHttpNode when a corporate proxy is present.
    # The requests library automatically tunnels HTTPS via the
    # HTTPS_PROXY env-var using HTTP CONNECT — no extra config needed.
    if _PROXY:
        log.info("Corporate proxy detected (%s) → using RequestsHttpNode", _PROXY)
        kwargs["node_class"] = RequestsHttpNode
    else:
        log.debug("No proxy detected — using default Urllib3HttpNode")

    host_url = f"{config.ES_SCHEME}://{config.ES_HOST}:{config.ES_PORT}"

    if config.uses_api_key:
        log.info("ES client → API key auth | %s", host_url)
        return Elasticsearch(
            host_url,
            api_key=config.ES_API_KEY,
            **kwargs,
        )
    else:
        log.info(
            "ES client → basic auth (user=%s) | %s",
            config.ES_USERNAME,
            host_url,
        )
        return Elasticsearch(
            hosts=[{
                "host":   config.ES_HOST,
                "port":   config.ES_PORT,
                "scheme": config.ES_SCHEME,
            }],
            basic_auth=config.es_auth,
            **kwargs,
        )
