"""
agents/cache.py
────────────────
Locality-scoped TTL cache for LLM lookups that only depend on a Bangalore
locality name (pricing benchmarks, neighbourhood facilities), not on the
full listing text. Avoids re-asking the LLM the same question for every
request in the same area.
"""

from __future__ import annotations

from threading import Lock
from typing import Callable, TypeVar

from cachetools import TTLCache

T = TypeVar("T")

_locality_cache: TTLCache = TTLCache(maxsize=256, ttl=3600)

# LangGraph runs pricing_node and neighbourhood_node concurrently on a
# ThreadPoolExecutor, and cachetools.TTLCache is not thread-safe internally
# (concurrent mutation of its eviction/expiry linked list raises a bare
# KeyError). This lock guards only the cache's own read/write operations;
# compute_fn() itself runs outside the lock so concurrent cold-key lookups
# can still compute in parallel.
_lock = Lock()


def cached_locality_lookup(cache_key: str, compute_fn: Callable[[], T]) -> T:
    """Returns the cached value for cache_key if present; otherwise calls
    compute_fn(), stores the result, and returns it."""
    with _lock:
        if cache_key in _locality_cache:
            return _locality_cache[cache_key]
    value = compute_fn()
    # ponytail: check-then-act race on a cold key means two threads can both
    # call compute_fn() and one write wins — an extra duplicate LLM call in
    # a rare race, not data corruption. Not worth a per-key lock for this.
    with _lock:
        _locality_cache[cache_key] = value
    return value


def clear_locality_cache() -> None:
    """Clears all cached entries. Used by tests to avoid cross-test pollution."""
    with _lock:
        _locality_cache.clear()
