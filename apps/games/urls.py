from django.urls import path
from . import views
from . import home_view
from . import search_view
from . import views_export
from . import settings_view
from . import health_view
from . import views_steam_detail

app_name = "games"

urlpatterns = [
    path("", home_view.home, name="home"),
    path("search/", search_view.steam_search, name="steam_search"),
    path("deals/", views.best_deals, name="best_deals"),
    path("settings/", settings_view.appearance_settings, name="appearance"),
    path("health/", health_view.health, name="health"),
    path("export/tracked.json", views_export.export_tracked_json, name="export_tracked"),
    path("api/suggest/", views.steam_suggest, name="steam_suggest"),
    path("api/platform/<int:app_id>/", views_steam_detail.platform_deals_api, name="platform_deals"),
    path("steam/<int:app_id>/", views_steam_detail.steam_detail, name="steam_detail"),
    path("track/steam/<int:app_id>/", views.track_steam, name="track_steam"),
    path("untrack/<slug:slug>/", views.untrack_game, name="untrack"),
    path("history/", views.history_page, name="history"),
    path("profile/", views.profile, name="profile"),
    path("game/<slug:slug>/", views.game_compare, name="compare"),
    path("watch/<slug:slug>/", views.watch_game, name="watch"),
    path("unwatch/<slug:slug>/", views.unwatch_game, name="unwatch"),
    path("alerts/clear/", views.clear_alerts, name="clear_alerts"),
]
