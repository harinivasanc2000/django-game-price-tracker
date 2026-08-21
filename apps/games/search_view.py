"""Search page — Steam plus console stores (filtered by platform)."""
from django.shortcuts import render

from .constants import PLATFORMS
from .models import BrowseHistory
from .platform_search import cheapest_hint, multi_platform_search
from .search_sort import sort_results
from .views import _log_history


def steam_search(request):
    q = request.GET.get("q", "").strip()
    country = request.GET.get("cc", "GB").strip().upper() or "GB"
    platform = request.GET.get("platform", "").strip().lower()
    sort = request.GET.get("sort", "relevance").strip().lower() or "relevance"

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

    if q:
        _log_history(request, BrowseHistory.Action.SEARCH, query=q)
        # Parallel multi-platform (only requested platforms)
        buckets = multi_platform_search(q, platform=platform, country=country, limit=10)
        results = sort_results(buckets.get("steam") or [], sort)
        best = cheapest_hint(buckets)
        if (
            not results
            and not buckets.get("psn")
            and not buckets.get("xbox")
            and not buckets.get("nintendo")
        ):
            error = "No close matches. Try another spelling, or pick a platform filter."

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
            "psn_results": buckets.get("psn") or [],
            "xbox_results": buckets.get("xbox") or [],
            "nintendo_results": buckets.get("nintendo") or [],
            "nintendo_blocked": buckets.get("nintendo_blocked", True),
            "nintendo_search_url": buckets.get("nintendo_search_url") or "",
            "platform_links": buckets.get("links") or [],
            "best_cross": best,
            "wide_layout": True,
        },
    )
