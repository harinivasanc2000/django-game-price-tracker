"""
Thin caching helpers shared by the store clients.

All external-network lookups go through `cached()` so a single Django
page render that calls the same store several times (e.g. the detail
page calling `deals_for_title` twice) only hits the network once.
"""

from __future__ import annotations

from typing import Callable, TypeVar

from django.core.cache import cache

T = TypeVar("T")


def cached(key: str, producer: Callable[[], T], timeout: int = 300) -> T:
    """Return the cached value for `key`, computing it via `producer` on a miss.

    Uses the configured Django cache (LocMem by default, Redis in
    production). A 0/falsy returned value (empty list / dict) is still
    cached briefly so blocked stores (Amazon/CeX/eBay WAF) are not
    re-hammered on every request.
    """
    value = cache.get(key)
    if value is not None:
        return value
    value = producer()
    cache.set(key, value, timeout)
    return value
