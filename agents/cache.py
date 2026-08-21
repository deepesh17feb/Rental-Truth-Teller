"""
agents/cache.py
────────────────
Locality-scoped TTL cache for LLM lookups that only depend on a Bangalore
locality name (pricing benchmarks, neighbourhood facilities), not on the
full listing text. Avoids re-asking the LLM the same question for every
request in the same area.
"""

from __future__ import annotations

from typing import Callable, TypeVar

from cachetools import TTLCache

T = TypeVar("T")

_locality_cache: TTLCache = TTLCache(maxsize=256, ttl=3600)


def cached_locality_lookup(cache_key: str, compute_fn: Callable[[], T]) -> T:
    """Returns the cached value for cache_key if present; otherwise calls
    compute_fn(), stores the result, and returns it."""
    if cache_key in _locality_cache:
        return _locality_cache[cache_key]
    value = compute_fn()
    _locality_cache[cache_key] = value
    return value


def clear_locality_cache() -> None:
    """Clears all cached entries. Used by tests to avoid cross-test pollution."""
    _locality_cache.clear()
