"""
Thin caching helpers shared by the store clients.

All external-network lookups go through `cached()` so a single Django
page render that calls the same store several times only hits the network once.

Empty / blocked results get a shorter TTL so we retry sooner without hammering.
"""

from __future__ import annotations

import hashlib
import re
import threading
from contextlib import contextmanager
from typing import Any, Callable, TypeVar

from django.core.cache import cache

T = TypeVar("T")

EMPTY_TTL = 90  # seconds — soft-fail stores (Amazon/CeX WAF) not re-hit every request
_MEMCACHE_SAFE_KEY = re.compile(r"^[A-Za-z0-9_.:-]{1,240}$")
_FLIGHT_GUARD = threading.Lock()
_FLIGHTS: dict[str, list[Any]] = {}
_CACHE_MISS = object()


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
    # Aggregate producers set this when their shared executor deadline expires.
    # Treat a partial response like an empty/blocked result so queue pressure
    # cannot poison a hot cache key for the normal full-result lifetime.
    if isinstance(value, dict) and value.get("_cache_incomplete") is True:
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


@contextmanager
def _single_flight(key: str):
    """Allow only one producer per cache key in this server process.

    A cache miss can otherwise make every simultaneous request scrape the same
    retailer.  Reference counts remove idle locks, so unique searches do not
    create an unbounded in-process lock registry.
    """
    with _FLIGHT_GUARD:
        state = _FLIGHTS.get(key)
        if state is None:
            state = [threading.RLock(), 0]
            _FLIGHTS[key] = state
        state[1] += 1
    lock = state[0]
    lock.acquire()
    try:
        yield
    finally:
        lock.release()
        with _FLIGHT_GUARD:
            state[1] -= 1
            if state[1] == 0 and _FLIGHTS.get(key) is state:
                _FLIGHTS.pop(key, None)


def cached(
    key: str,
    producer: Callable[[], T],
    timeout: int = 300,
    *,
    empty_timeout: int = EMPTY_TTL,
) -> T:
    """Return a cached value with duplicate in-process producers collapsed."""
    key = _cache_key(key)
    # A producer may legitimately return ``None`` (for example a missing Steam
    # app). A private sentinel lets that negative result use the short empty TTL
    # instead of triggering another external request on every page load.
    value = cache.get(key, _CACHE_MISS)
    if value is not _CACHE_MISS:
        return value
    with _single_flight(key):
        # The first thread may have populated the cache while this one waited.
        value = cache.get(key, _CACHE_MISS)
        if value is not _CACHE_MISS:
            return value
        value = producer()
        ttl = empty_timeout if _is_empty(value) else timeout
        cache.set(key, value, ttl)
        return value


def bust(prefix: str) -> None:
    """Best-effort key delete for LocMem / Redis (exact key only)."""
    try:
        cache.delete(prefix)
    except Exception:
        pass
