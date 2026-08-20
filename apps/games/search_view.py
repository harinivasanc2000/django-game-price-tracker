from django.shortcuts import render

from .models import BrowseHistory
from .clients.steam import search_store
from .clients.uk_stores import platform_query
from .search_sort import sort_results
from .views import _log_history, PLATFORMS


def steam_search(request):
    q = request.GET.get("q", "").strip()
    country = request.GET.get("cc", "GB").strip().upper() or "GB"
    platform = request.GET.get("platform", "").strip().lower()
    sort = request.GET.get("sort", "relevance").strip().lower() or "relevance"
    results, error = [], None
    if q:
        _log_history(request, BrowseHistory.Action.SEARCH, query=q)
        search_q = platform_query(q, platform) if platform else q
        results = search_store(search_q, country=country, limit=40)
        results = sort_results(results, sort)
        if not results:
            error = "No close matches. Try another spelling or a fuller title."
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
        },
    )
