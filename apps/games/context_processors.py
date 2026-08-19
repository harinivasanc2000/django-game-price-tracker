from .models import SiteSettings, Game


def site_ui(request):
    try:
        settings_obj = SiteSettings.load()
    except Exception:
        settings_obj = None

    tracked = []
    try:
        tracked = list(
            Game.objects.filter(is_active=True).order_by("title")[:40]
        )
    except Exception:
        pass

    return {
        "site_settings": settings_obj,
        "tracked_drawer": tracked,
        "tracked_count": len(tracked),
    }
