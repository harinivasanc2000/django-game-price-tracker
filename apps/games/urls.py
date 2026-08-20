from django.urls import path
from . import views

app_name = "games"

urlpatterns = [
    path("", views.home, name="home"),
    path("search/", views.steam_search, name="steam_search"),
    path("deals/", views.best_deals, name="best_deals"),
    path("api/suggest/", views.steam_suggest, name="steam_suggest"),
    path("api/platform/<int:app_id>/", views.platform_deals_api, name="platform_deals"),
    path("steam/<int:app_id>/", views.steam_detail, name="steam_detail"),
    path("track/steam/<int:app_id>/", views.track_steam, name="track_steam"),
    path("untrack/<slug:slug>/", views.untrack_game, name="untrack"),
    path("history/", views.history_page, name="history"),
    path("profile/", views.profile, name="profile"),
    path("game/<slug:slug>/", views.game_compare, name="compare"),
    path("watch/<slug:slug>/", views.watch_game, name="watch"),
    path("unwatch/<slug:slug>/", views.unwatch_game, name="unwatch"),
    path("alerts/clear/", views.clear_alerts, name="clear_alerts"),
]
