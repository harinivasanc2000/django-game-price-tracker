"""Client-side appearance settings — no login required."""
from django.shortcuts import render


def appearance_settings(request):
    return render(request, "games/settings.html")
