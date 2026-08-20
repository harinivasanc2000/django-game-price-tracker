"""Home page with tracked, popular, and recently viewed."""
from django.contrib import messages
from django.shortcuts import render

from .models import Game, BrowseHistory
from .views_home_extra import recent_views_for_session

POPULAR_APP_IDS = [
    1091500, 1245620, 271590, 1174180, 1593500, 1086940,
    292030, 1817070, 814380, 1113000, 108710, 1145360,
]

PLATFORMS = [
    ("", "All"),
    ("pc", "PC"),
    ("ps4", "PS4"),
    ("ps5", "PS5"),
    ("xbox", "Xbox"),
    ("switch", "Switch"),
]


def home(request):
    list(messages.get_messages(request))
    platform = request.GET.get("platform", "").strip().lower()
    tracked = list(Game.objects.filter(is_active=True).order_by("title")[:12])
    tracked_ids = {g.steam_app_id for g in tracked if g.steam_app_id}
    popular = list(
        Game.objects.filter(steam_app_id__in=POPULAR_APP_IDS).exclude(steam_app_id__in=tracked_ids)
    )
    order = {aid: i for i, aid in enumerate(POPULAR_APP_IDS)}
    popular.sort(key=lambda g: order.get(g.steam_app_id, 999))

    if not request.session.session_key:
        request.session.create()
    recent = recent_views_for_session(request.session.session_key, limit=8)

    return render(
        request,
        "games/home.html",
        {
            "tracked_home": tracked,
            "popular": popular,
            "platforms": PLATFORMS,
            "current_platform": platform,
            "recent_views": recent,
        },
    )
