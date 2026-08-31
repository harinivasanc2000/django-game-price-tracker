"""
Parallel multi-platform search — Steam + PSN + Xbox + Nintendo.

Light by design:
  - short client timeouts + hard 6s pool deadline
  - client caches + one raw-result cache reused by every display filter
  - modest capped over-fetch for strict title filtering
  - soft-fail per platform
  - strict title_match, platform metadata filtering, and stable deduplication
"""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from concurrent.futures import as_completed
from decimal import Decimal
from typing import Any
from urllib.parse import quote, quote_plus

from django.core.cache import cache

from .clients.digital_stores_bs4 import digital_search_links
from .clients.nintendo import nintendo_search_url, search_nintendo
from .clients.psn import search_psn
from .clients.steam import search_store
from .clients.title_match import filter_by_title
from .clients.uk_stores import platform_query, uk_search_links
from .clients.xbox import microsoft_store_search_url, search_xbox, xbox_search_url
from .fx import to_gbp_or_zero
from .executors import PAGE_EXECUTOR, cancel_pending

MPS_TTL = 240  # 4 min — search is hot path
POOL_TIMEOUT = 6.0
_ALLOWED_PLATFORMS = frozenset({"", "pc", "ps4", "ps5", "xbox", "switch"})
_ALLOWED_AVAILABILITY = frozenset({"any", "priced", "free"})


def normalise_search_query(value: str | None) -> str:
    """Canonicalise user text for APIs, matching, history, and cache identity."""
    text = unicodedata.normalize("NFKC", value or "")
    # Store search endpoints gain nothing from control characters or repeated
    # whitespace. Keeping punctuation is useful for titles such as ``F.E.A.R.``.
    # Replace controls with a separator instead of deleting them: ``Hades\nII``
    # must not become the different token ``HadesII``.
    text = "".join(" " if unicodedata.category(ch) == "Cc" else ch for ch in text)
    return re.sub(r"\s+", " ", text).strip()[:120]


def _cache_key(query: str, platform: str, country: str, fetch_n: int) -> str:
    """Build a backend-safe fixed-length key (Memcached caps keys at 250 bytes)."""
    identity = f"{query.casefold()}|{platform}|{country}|{fetch_n}"
    digest = hashlib.blake2s(identity.encode("utf-8"), digest_size=12).hexdigest()
    return f"mps:v6:{digest}"


def _ser(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        if isinstance(v, Decimal):
            out[k] = float(v)
        else:
            out[k] = v
    return out


def _usable_price(row: dict) -> float | None:
    """Normalise cross-store price fields and reject non-finite placeholders."""
    status = str(row.get("price_status") or "").lower()
    if status == "free":
        return 0.0
    if status == "unknown" or row.get("has_price") is False:
        return None
    try:
        price = float(row["price"]) if row.get("price") is not None else None
    except (TypeError, ValueError, OverflowError):
        return None
    if price is None or not math.isfinite(price) or price < 0:
        return None
    return price


def _is_free(row: dict, price: float | None) -> bool:
    status = str(row.get("price_status") or "").lower()
    return status == "free" or (
        price == 0 and status != "unknown" and row.get("has_price") is not False
    )


def _price_filter_rows(
    rows: list[dict],
    *,
    min_price: float | None = None,
    max_price: float | None = None,
    hide_free: bool = False,
    availability: str = "any",
    min_discount: int = 0,
) -> list[dict]:
    """Apply one consistent price policy to all four platform result shapes."""
    availability = (availability or "any").strip().lower()
    if availability not in _ALLOWED_AVAILABILITY:
        availability = "any"
    try:
        min_discount = max(0, min(int(min_discount or 0), 100))
    except (TypeError, ValueError, OverflowError):
        min_discount = 0
    if (
        min_price is None
        and max_price is None
        and not hide_free
        and availability == "any"
        and min_discount == 0
    ):
        return list(rows)

    out = []
    for row in rows:
        price = _usable_price(row)
        free = _is_free(row, price)

        if hide_free and free:
            continue
        if availability == "priced" and (price is None or price <= 0):
            continue
        if availability == "free" and not free:
            continue

        # A requested band necessarily requires a known numeric price. The old
        # max-only branch retained unknown rows, which made "Under £10" misleading.
        if min_price is not None or max_price is not None:
            if price is None:
                continue
            if min_price is not None and price < min_price:
                continue
            if max_price is not None and price > max_price:
                continue

        if min_discount:
            try:
                discount = float(row.get("discount") or 0)
            except (TypeError, ValueError, OverflowError):
                discount = 0.0
            if not math.isfinite(discount) or discount < min_discount:
                continue

        out.append(row)
    return out


def _filter_psn_generation(rows: list[dict], platform: str) -> list[dict]:
    """Respect PS4/PS5 metadata when PSN supplies it, retaining unknown rows."""
    if platform not in {"ps4", "ps5"}:
        return rows
    wanted = "4" if platform == "ps4" else "5"
    out = []
    for row in rows:
        labels = " ".join(str(value) for value in (row.get("platforms") or []))
        compact = re.sub(r"[^a-z0-9]", "", labels.casefold())
        mentions_ps = "ps4" in compact or "ps5" in compact or "playstation" in compact
        matches = f"ps{wanted}" in compact or f"playstation{wanted}" in compact
        if not mentions_ps or matches:
            out.append(row)
    return out


def _dedupe_rows(rows: list[dict]) -> list[dict]:
    """Remove repeated aliases while preserving the client's ranked order."""
    seen: set[str] = set()
    out: list[dict] = []
    for row in rows:
        identity = (
            row.get("app_id")
            or row.get("product_id")
            or row.get("url")
            or f"{str(row.get('name') or '').casefold()}|{row.get('price')}"
        )
        marker = str(identity)
        if marker in seen:
            continue
        seen.add(marker)
        out.append(row)
    return out


def _outbound_search_links(
    query: str,
    platform: str,
    nintendo_url: str,
    *,
    min_price: float | None,
    max_price: float | None,
    condition: str,
) -> list[dict[str, str]]:
    """Build encoded UK storefront fallbacks, grouped for an accessible UI."""
    encoded = quote_plus(query)
    path_encoded = quote(query, safe="")
    official = [
        {
            "name": "Steam",
            "platform": "pc",
            "kind": "official",
            "note": "Official PC store",
            "url": f"https://store.steampowered.com/search/?term={encoded}&cc=gb",
        },
        {
            "name": "PlayStation Store UK",
            "platform": "ps5",
            "kind": "official",
            "note": "Official PS4 / PS5 store",
            "url": f"https://store.playstation.com/en-gb/search/{path_encoded}",
        },
        {
            "name": "Xbox UK",
            "platform": "xbox",
            "kind": "official",
            "note": "Official Xbox store",
            "url": xbox_search_url(query),
        },
        {
            "name": "Microsoft Store UK",
            "platform": "xbox",
            "kind": "official",
            "note": "Windows and Xbox games",
            "url": microsoft_store_search_url(query),
        },
        {
            "name": "Nintendo eShop UK",
            "platform": "switch",
            "kind": "official",
            "note": "Official Nintendo store",
            "url": nintendo_url or nintendo_search_url(query),
        },
    ]
    if platform:
        accepted = {platform}
        if platform in {"ps4", "ps5"}:
            accepted.update({"ps4", "ps5"})
        official = [link for link in official if link["platform"] in accepted]

    links: list[dict[str, str]] = []
    for link in official:
        links.append({**link, "group": "Official UK storefronts"})

    if platform in {"", "pc"}:
        for link in digital_search_links(query):
            links.append(
                {
                    **link,
                    "platform": "pc",
                    "group": "PC stores & comparison",
                    "note": (
                        "Compare seller reputation before buying"
                        if link.get("kind") in {"third-party", "meta"}
                        else "Authorised or official digital search"
                    ),
                }
            )

    for link in uk_search_links(
        query,
        platform,
        min_price=min_price,
        max_price=max_price,
        condition=condition,
    ):
        links.append({**link, "platform": platform, "group": "UK shops & marketplaces"})

    # Some store helpers intentionally overlap. A stable first-win dedupe keeps
    # the page compact without throwing away the safer official entry.
    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, str]] = []
    for link in links:
        marker = (link.get("name", "").casefold(), link.get("url", ""))
        if marker in seen or not link.get("url"):
            continue
        seen.add(marker)
        unique.append(link)
    return unique


def multi_platform_search(
    query: str,
    *,
    platform: str = "",
    country: str = "GB",
    limit: int = 8,
    min_price: float | None = None,
    max_price: float | None = None,
    hide_dlc: bool = False,
    hide_free: bool = False,
    availability: str = "any",
    min_discount: int = 0,
    condition: str = "",
) -> dict[str, Any]:
    q = normalise_search_query(query)
    plat = (platform or "").strip().lower()
    if plat not in _ALLOWED_PLATFORMS:
        plat = ""
    country = (country or "GB").strip().upper()
    if not re.fullmatch(r"[A-Z]{2}", country):
        country = "GB"
    try:
        limit = max(4, min(int(limit or 8), 16))
    except (TypeError, ValueError, OverflowError):
        limit = 8
    availability = (availability or "any").strip().lower()
    if availability not in _ALLOWED_AVAILABILITY:
        availability = "any"
    try:
        min_discount = max(0, min(int(min_discount or 0), 100))
    except (TypeError, ValueError, OverflowError):
        min_discount = 0
    condition = (condition or "").strip().lower()
    if condition not in {"", "new", "used"}:
        condition = ""

    empty = {
        "steam": [],
        "psn": [],
        "xbox": [],
        "nintendo": [],
        "links": [],
        "nintendo_blocked": True,
        "nintendo_search_url": nintendo_search_url(q) if q else "",
        "query": q,
        "platform": plat,
    }
    if not q:
        return empty

    want_steam = plat in ("", "pc")
    want_psn = plat in ("", "ps4", "ps5")
    want_xbox = plat in ("", "xbox")
    want_switch = plat in ("", "switch")

    # Steam is already a PC-only source. Adding "PC" to the title reduced
    # exact API matches, while a generation hint remains useful for PSN.
    steam_q = q
    psn_q = platform_query(q, plat) if plat.startswith("ps") else q
    fetch_n = max(limit + 4, 10)  # modest over-fetch for title_match
    cache_key = _cache_key(q, plat, country, fetch_n)
    raw = cache.get(cache_key)

    if raw is None:
        steam_rows: list = []
        psn_rows: list = []
        xbox_rows: list = []
        nint_block: dict = {
            "results": [],
            "blocked": True,
            "search_url": nintendo_search_url(q),
        }

        def run_steam():
            try:
                return search_store(steam_q, country=country, limit=fetch_n)
            except Exception:
                return []

        def run_psn():
            try:
                return search_psn(psn_q, limit=fetch_n)
            except Exception:
                return []

        def run_xbox():
            try:
                return search_xbox(q, limit=fetch_n)
            except Exception:
                return []

        def run_nint():
            try:
                return search_nintendo(q, limit=min(fetch_n, 10))
            except Exception:
                return {
                    "results": [],
                    "blocked": True,
                    "search_url": nintendo_search_url(q),
                }

        futures = {}
        if want_steam:
            futures[PAGE_EXECUTOR.submit(run_steam)] = "steam"
        if want_psn:
            futures[PAGE_EXECUTOR.submit(run_psn)] = "psn"
        if want_xbox:
            futures[PAGE_EXECUTOR.submit(run_xbox)] = "xbox"
        if want_switch:
            futures[PAGE_EXECUTOR.submit(run_nint)] = "nint"

        completed_count = 0
        try:
            for future in as_completed(futures, timeout=POOL_TIMEOUT):
                completed_count += 1
                kind = futures[future]
                try:
                    result = future.result()
                except Exception:
                    continue
                if kind == "steam":
                    steam_rows = result or []
                elif kind == "psn":
                    psn_rows = result or []
                elif kind == "xbox":
                    xbox_rows = result or []
                elif kind == "nint":
                    nint_block = result or nint_block
        except TimeoutError:
            # Completed platforms are still useful; slow clients soft-fail.
            pass
        finally:
            cancel_pending(futures)

        raw = {
            "steam": [_ser(row) for row in steam_rows],
            "psn": [_ser(row) for row in psn_rows],
            "xbox": [_ser(row) for row in xbox_rows],
            "nintendo": [_ser(row) for row in (nint_block.get("results") or [])],
            "nintendo_blocked": bool(nint_block.get("blocked")),
            "nintendo_search_url": nint_block.get("search_url") or nintendo_search_url(q),
        }
        # Only network/title inputs belong in this cache. Price, condition and
        # display filters are inexpensive and now reuse the same raw response.
        # A saturated shared pool is not evidence of zero search results: keep
        # that partial response for only a few seconds so the next request can
        # retry after queue pressure clears.
        cache.set(cache_key, raw, 15 if completed_count < len(futures) else MPS_TTL)

    steam_rows = _dedupe_rows(filter_by_title(raw.get("steam") or [], q, min_score=0.67))
    if hide_dlc:
        steam_rows = [r for r in steam_rows if not r.get("is_likely_dlc")]
    steam_rows = _price_filter_rows(
        steam_rows,
        min_price=min_price,
        max_price=max_price,
        hide_free=hide_free,
        availability=availability,
        min_discount=min_discount,
    )[:limit]

    psn_rows = _dedupe_rows(filter_by_title(raw.get("psn") or [], q, min_score=0.67))
    psn_rows = _filter_psn_generation(psn_rows, plat)
    if hide_dlc:
        psn_rows = [row for row in psn_rows if row.get("is_full_game") is not False]
    psn_rows = _price_filter_rows(
        psn_rows,
        min_price=min_price,
        max_price=max_price,
        hide_free=hide_free,
        availability=availability,
        min_discount=min_discount,
    )[:limit]

    xbox_rows = _dedupe_rows(filter_by_title(raw.get("xbox") or [], q, min_score=0.67))
    xbox_rows = _price_filter_rows(
        xbox_rows,
        min_price=min_price,
        max_price=max_price,
        hide_free=hide_free,
        availability=availability,
        min_discount=min_discount,
    )[:limit]

    nint_rows = _dedupe_rows(
        filter_by_title(raw.get("nintendo") or [], q, min_score=0.67)
    )
    nint_rows = _price_filter_rows(
        nint_rows,
        min_price=min_price,
        max_price=max_price,
        hide_free=hide_free,
        availability=availability,
        min_discount=min_discount,
    )[:limit]

    nintendo_url = raw.get("nintendo_search_url") or nintendo_search_url(q)
    links = _outbound_search_links(
        q,
        plat,
        nintendo_url,
        min_price=min_price,
        max_price=max_price,
        condition=condition,
    )

    payload = {
        "steam": steam_rows,
        "psn": psn_rows,
        "xbox": xbox_rows,
        "nintendo": nint_rows,
        "nintendo_blocked": bool(raw.get("nintendo_blocked")) and not nint_rows,
        "nintendo_search_url": nintendo_url,
        "links": links,
        "query": q,
        "platform": plat,
    }
    return payload


def cheapest_hint(buckets: dict[str, Any]) -> dict[str, Any] | None:
    """Return the cheapest trustworthy paid result converted to GBP."""
    candidates: list[dict[str, Any]] = []

    def add(platform_name: str, row: dict, url: str | None = None) -> None:
        price = _usable_price(row)
        if price is None or price <= 0:
            return
        try:
            gbp = float(to_gbp_or_zero(price, row.get("currency") or "GBP"))
        except (TypeError, ValueError, OverflowError):
            return
        if not math.isfinite(gbp) or gbp <= 0:
            return
        candidates.append(
            {
                "platform": platform_name,
                "title": row.get("name"),
                "price_gbp": gbp,
                "url": url if url is not None else row.get("url"),
            }
        )

    for row in buckets.get("steam") or []:
        detail_url = f"/steam/{row.get('app_id')}/" if row.get("app_id") else row.get("url")
        add("PC / Steam", row, detail_url)
    for row in buckets.get("psn") or []:
        add("PlayStation", row)
    for row in buckets.get("xbox") or []:
        add("Xbox", row)
    for row in buckets.get("nintendo") or []:
        add("Switch", row)

    if not candidates:
        return None
    candidates.sort(key=lambda item: (item["price_gbp"], item.get("title") or ""))
    return candidates[0]
