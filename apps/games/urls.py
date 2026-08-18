from django.urls import path
from . import views

app_name = "games"

urlpatterns = [
    path("", views.home, name="home"),
    path("game/<slug:slug>/", views.game_compare, name="compare"),
]
