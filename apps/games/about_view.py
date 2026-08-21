"""About / feature list — helps you and future-you understand the app."""
from django.shortcuts import render


def about(request):
    return render(
        request,
        "games/about.html",
        {"wide_layout": True},
    )
