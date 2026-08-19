from django.urls import path
from . import views

app_name = "games"

urlpatterns = [
    path("", views.home, name="home"),
    path("search/", views.steam_search, name="steam_search"),
    path("track/steam/<int:app_id>/", views.track_steam, name="track_steam"),
    path("game/<slug:slug>/", views.game_compare, name="compare"),
]
