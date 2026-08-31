"""Small process-wide pools for bounded external I/O.

Creating nested ThreadPoolExecutors per request lets a burst of unique searches
leave dozens of timed-out socket threads behind.  These pools are shared by all
requests in one Django/Celery process, start threads lazily, and put a hard cap
on total external-I/O concurrency.  Separate orchestration layers avoid the
deadlock risk of a task waiting for child work in its own saturated pool.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor


def _workers(name: str, default: int, maximum: int) -> int:
    try:
        requested = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        requested = default
    return max(1, min(requested, maximum))


# Page-level jobs: home cards, detail side feeds, and cross-platform search.
PAGE_EXECUTOR = ThreadPoolExecutor(
    max_workers=_workers("PAGE_IO_WORKERS", 6, 12),
    thread_name_prefix="page-io",
)

# One platform bundle fans out to official APIs, Amazon, and one UK aggregate.
BUNDLE_EXECUTOR = ThreadPoolExecutor(
    max_workers=_workers("BUNDLE_IO_WORKERS", 5, 8),
    thread_name_prefix="bundle-io",
)

# The eleven public UK sources share six workers instead of one thread each.
UK_EXECUTOR = ThreadPoolExecutor(
    max_workers=_workers("UK_IO_WORKERS", 6, 11),
    thread_name_prefix="uk-store-io",
)


def cancel_pending(futures) -> None:
    """Best-effort cancellation for work that has not started by a deadline."""
    for future in futures:
        if not future.done():
            future.cancel()
