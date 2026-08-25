"""Lightweight health check for local monitoring."""
from __future__ import annotations

from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.utils import timezone

from .models import Game


def health(request):
    ok = True
    checks: dict = {}

    try:
        with connection.cursor() as c:
            c.execute("SELECT 1")
            c.fetchone()
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e.__class__.__name__}"
        ok = False

    try:
        cache.set("health:ping", "1", 10)
        checks["cache"] = "ok" if cache.get("health:ping") == "1" else "miss"
    except Exception as e:
        checks["cache"] = f"error: {e.__class__.__name__}"
        ok = False

    try:
        checks["tracked_active"] = Game.objects.filter(is_active=True).count()
    except Exception:
        checks["tracked_active"] = None

    # Optional shallow store pings (?stores=1) — not for production probes every second
    if request.GET.get("stores") in ("1", "true", "yes"):
        stores: dict[str, str] = {}
        try:
            from .clients.scrape_utils import fetch_json

            data, status = fetch_json(
                "https://wss2.cex.uk.webuy.io/v3/boxes",
                params={"q": "god of war", "firstRecord": 1, "count": 1},
                timeout=4,
            )
            stores["cex_api"] = "ok" if status == 200 and data else f"status_{status}"
        except Exception as e:
            stores["cex_api"] = f"error:{e.__class__.__name__}"
        try:
            from .clients.steam import search_store

            rows = search_store("hades", country="GB", limit=1)
            stores["steam"] = "ok" if rows else "empty"
        except Exception as e:
            stores["steam"] = f"error:{e.__class__.__name__}"
        checks["stores"] = stores

    return JsonResponse(
        {
            "status": "ok" if ok else "degraded",
            "time": timezone.now().isoformat(),
            "checks": checks,
        },
        status=200 if ok else 503,
    )
