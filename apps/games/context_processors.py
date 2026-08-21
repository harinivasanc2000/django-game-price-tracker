"""
Global template context — kept intentionally light.

Avoid loading full Game rows / related objects on every page.
"""
from __future__ import annotations

from django.core.cache import cache

from .models import Game, SiteSettings


def site_ui(request):
    # Site settings: cache 5 minutes (admin changes are rare)
    settings_obj = cache.get("site_settings:v1")
    if settings_obj is None:
        try:
            settings_obj = SiteSettings.load()
        except Exception:
            settings_obj = None
        cache.set("site_settings:v1", settings_obj, 300)

    # Tracked drawer: only columns the template needs, max 30, cached 60s
    tracked = cache.get("tracked_drawer:v1")
    if tracked is None:
        try:
            tracked = list(
                Game.objects.filter(is_active=True)
                .only(
                    "title",
                    "slug",
                    "steam_app_id",
                    "platform",
                    "launch_price",
                    "launch_currency",
                    "cover_url",
                )
                .order_by("title")[:30]
            )
        except Exception:
            tracked = []
        cache.set("tracked_drawer:v1", tracked, 60)

    return {
        "site_settings": settings_obj,
        "tracked_drawer": tracked,
        "tracked_count": len(tracked),
    }
