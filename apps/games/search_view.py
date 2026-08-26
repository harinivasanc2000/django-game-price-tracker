"""Search page — Steam plus console stores with server-side filters."""
from __future__ import annotations

from django.shortcuts import render

from .clients.scrape_filters import parse_price_bound
from .constants import PLATFORMS
from .models import BrowseHistory
from .platform_search import cheapest_hint, multi_platform_search
from .search_sort import sort_results
from .views import _log_history, _session_key


def steam_search(request):
    q = request.GET.get("q", "").strip()[:120]
    country = request.GET.get("cc", "GB").strip().upper() or "GB"
    platform = request.GET.get("platform", "").strip().lower()
    sort = request.GET.get("sort", "relevance").strip().lower() or "relevance"

    min_price = parse_price_bound(request.GET.get("min_price"))
    max_price = parse_price_bound(request.GET.get("max_price"))
    hide_dlc = request.GET.get("hide_dlc", "1") not in ("0", "false", "off")
    hide_free = request.GET.get("hide_free") in ("1", "true", "on")

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
            .values_list("query", flat=True)[:8]
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
            limit=10,
            min_price=lo,
            max_price=hi,
            hide_dlc=hide_dlc,
            hide_free=hide_free,
        )
        results = sort_results(buckets.get("steam") or [], sort)
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
            "min_price": request.GET.get("min_price", ""),
            "max_price": request.GET.get("max_price", ""),
            "hide_dlc": hide_dlc,
            "hide_free": hide_free,
            "psn_results": buckets.get("psn") or [],
            "xbox_results": buckets.get("xbox") or [],
            "nintendo_results": buckets.get("nintendo") or [],
            "nintendo_blocked": buckets.get("nintendo_blocked", True),
            "nintendo_search_url": buckets.get("nintendo_search_url") or "",
            "platform_links": buckets.get("links") or [],
            "best_cross": best,
            "recent_searches": recent,
            "wide_layout": True,
        },
    )
