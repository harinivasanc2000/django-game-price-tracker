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

    # DB
    try:
        with connection.cursor() as c:
            c.execute("SELECT 1")
            c.fetchone()
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e.__class__.__name__}"
        ok = False

    # Cache
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

    return JsonResponse(
        {
            "status": "ok" if ok else "degraded",
            "time": timezone.now().isoformat(),
            "checks": checks,
        },
        status=200 if ok else 503,
    )
