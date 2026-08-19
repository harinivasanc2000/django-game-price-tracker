from django.urls import path
from . import views

app_name = "games"

urlpatterns = [
    path("", views.home, name="home"),
    path("search/", views.steam_search, name="steam_search"),
    path("steam/<int:app_id>/", views.steam_detail, name="steam_detail"),
    path("track/steam/<int:app_id>/", views.track_steam, name="track_steam"),
    path("history/", views.history_page, name="history"),
    path("game/<slug:slug>/", views.game_compare, name="compare"),
]
