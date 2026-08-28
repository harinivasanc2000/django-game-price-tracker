"""Search page — Steam plus console stores with server-side filters."""
from __future__ import annotations

from decimal import Decimal

from django.shortcuts import render

from .clients.scrape_filters import parse_price_bound
from .constants import PLATFORMS
from .models import BrowseHistory
from .platform_search import cheapest_hint, multi_platform_search, normalise_search_query
from .search_sort import normalise_sort, sort_results
from .views import _log_history, _session_key


_PLATFORM_VALUES = frozenset(value for value, _label in PLATFORMS)
_AVAILABILITY_VALUES = frozenset({"any", "priced", "free"})
_CONDITION_VALUES = frozenset({"", "new", "used"})
_RESULT_LIMITS = (5, 10, 16)


def _bool_param(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "on", "yes"}


def _price_bound(raw: str | None) -> Decimal | None:
    """Use the shared parser, additionally rejecting Infinity/NaN."""
    value = parse_price_bound(raw)
    return value if value is not None and value.is_finite() else None


def _bounded_int(raw: str | None, *, default: int, low: int, high: int) -> int:
    try:
        value = int(raw) if raw not in (None, "") else default
    except (TypeError, ValueError, OverflowError):
        return default
    return max(low, min(value, high))


def _decimal_text(value: Decimal | None) -> str:
    if value is None:
        return ""
    return format(value.normalize(), "f")


def steam_search(request):
    q = normalise_search_query(request.GET.get("q", ""))
    # Every non-Steam source and retailer link on this page is UK-specific.
    country = "GB"
    platform = request.GET.get("platform", "").strip().lower()
    if platform not in _PLATFORM_VALUES:
        platform = ""
    sort = normalise_sort(request.GET.get("sort"))

    min_raw = request.GET.get("min_price")
    max_raw = request.GET.get("max_price")
    min_price = _price_bound(min_raw)
    max_price = _price_bound(max_raw)
    notices: list[str] = []
    if min_raw and min_price is None:
        notices.append("The invalid minimum price was ignored.")
    if max_raw and max_price is None:
        notices.append("The invalid maximum price was ignored.")
    if min_price is not None and max_price is not None and min_price > max_price:
        min_price, max_price = max_price, min_price
        notices.append("Minimum and maximum prices were swapped into the correct order.")

    hide_dlc = _bool_param(request.GET.get("hide_dlc"), default=True)
    hide_free = _bool_param(request.GET.get("hide_free"))  # legacy shared links
    availability = request.GET.get("availability", "any").strip().lower()
    if availability not in _AVAILABILITY_VALUES:
        availability = "any"
    if availability == "free":
        hide_free = False
    min_discount = _bounded_int(
        request.GET.get("min_discount"), default=0, low=0, high=100
    )
    condition = request.GET.get("condition", "").strip().lower()
    if condition not in _CONDITION_VALUES:
        condition = ""
    requested_limit = _bounded_int(
        request.GET.get("limit"), default=10, low=4, high=16
    )
    limit = min(_RESULT_LIMITS, key=lambda value: abs(value - requested_limit))

    lo = float(min_price) if min_price is not None else None
    hi = float(max_price) if max_price is not None else None

    results, error = [], None
    buckets = {
        "steam": [],
        "psn": [],
        "xbox": [],
        "nintendo": [],
        "links": [],
        "nintendo_blocked": True,
        "nintendo_search_url": "",
    }
    best = None

    recent: list[str] = []
    if not q:
        # Lightweight recent queries for empty state (no extra network)
        recent = list(
            BrowseHistory.objects.filter(
                session_key=_session_key(request),
                action=BrowseHistory.Action.SEARCH,
            )
            .exclude(query="")
            .order_by("-created_at")
            .values_list("query", flat=True)[:24]
        )
        # de-dupe preserve order
        seen = set()
        deduped = []
        for r in recent:
            k = r.lower()
            if k not in seen:
                seen.add(k)
                deduped.append(r)
        recent = deduped[:6]

    if q:
        _log_history(request, BrowseHistory.Action.SEARCH, query=q)
        buckets = multi_platform_search(
            q,
            platform=platform,
            country=country,
            limit=limit,
            min_price=lo,
            max_price=hi,
            hide_dlc=hide_dlc,
            hide_free=hide_free,
            availability=availability,
            min_discount=min_discount,
            condition=condition,
        )
        # Apply the selected ordering consistently instead of sorting Steam only.
        for bucket_name in ("steam", "psn", "xbox", "nintendo"):
            buckets[bucket_name] = sort_results(buckets.get(bucket_name) or [], sort)
        results = buckets["steam"]
        best = cheapest_hint(buckets)
        if (
            not results
            and not buckets.get("psn")
            and not buckets.get("xbox")
            and not buckets.get("nintendo")
        ):
            error = "No close matches. Try another spelling, clear price filters, or change platform."

    return render(
        request,
        "games/steam_search.html",
        {
            "q": q,
            "results": results,
            "error": error,
            "country": country,
            "platforms": PLATFORMS,
            "current_platform": platform,
            "sort": sort,
            "min_price": _decimal_text(min_price),
            "max_price": _decimal_text(max_price),
            "hide_dlc": hide_dlc,
            "hide_free": hide_free,
            "availability": availability,
            "min_discount": min_discount,
            "condition": condition,
            "result_limit": limit,
            "result_limits": _RESULT_LIMITS,
            "filter_notices": notices,
            "psn_results": buckets.get("psn") or [],
            "xbox_results": buckets.get("xbox") or [],
            "nintendo_results": buckets.get("nintendo") or [],
            "nintendo_blocked": buckets.get("nintendo_blocked", True),
            "nintendo_search_url": buckets.get("nintendo_search_url") or "",
            "platform_links": buckets.get("links") or [],
            "best_cross": best,
            "result_count": sum(
                len(buckets.get(name) or [])
                for name in ("steam", "psn", "xbox", "nintendo")
            ),
            "has_active_filters": bool(
                min_price is not None
                or max_price is not None
                or availability != "any"
                or min_discount
                or condition
                or not hide_dlc
                or sort != "relevance"
                or limit != 10
            ),
            "recent_searches": recent,
            "wide_layout": True,
        },
    )
