"""
Thin caching helpers shared by the store clients.

All external-network lookups go through `cached()` so a single Django
page render that calls the same store several times only hits the network once.

Empty / blocked results get a shorter TTL so we retry sooner without hammering.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Callable, TypeVar

from django.core.cache import cache

T = TypeVar("T")

EMPTY_TTL = 90  # seconds — soft-fail stores (Amazon/CeX WAF) not re-hit every request
_MEMCACHE_SAFE_KEY = re.compile(r"^[A-Za-z0-9_.:-]{1,240}$")


def _cache_key(key: str) -> str:
    """Make externally-derived cache keys safe for every Django cache backend.

    Store titles commonly include spaces, Unicode, or punctuation. LocMem
    accepts them, while Memcached rejects them, so hash only unsafe keys.
    """
    key = str(key)
    if _MEMCACHE_SAFE_KEY.fullmatch(key):
        return key
    return "gpt:" + hashlib.sha256(key.encode("utf-8")).hexdigest()


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (list, tuple, set, dict, str)) and len(value) == 0:
        return True
    if isinstance(value, dict):
        # UK / Nintendo style: {"results": [], "blocked": True, ...}
        if "results" in value and not value.get("results"):
            return True
        if value.get("blocked") is True and not value.get("results"):
            return True
    return False


def cached(key: str, producer: Callable[[], T], timeout: int = 300) -> T:
    """Return the cached value for `key`, computing it via `producer` on a miss."""
    key = _cache_key(key)
    value = cache.get(key)
    if value is not None:
        return value
    value = producer()
    ttl = EMPTY_TTL if _is_empty(value) else timeout
    cache.set(key, value, ttl)
    return value


def bust(prefix: str) -> None:
    """Best-effort key delete for LocMem / Redis (exact key only)."""
    try:
        cache.delete(prefix)
    except Exception:
        pass
