"""Research lab page: ML plans for enthusiasts & programmers. No training here."""
from django.shortcuts import render


def research_lab(request):
    return render(
        request,
        "games/research.html",
        {
            "wide_layout": True,
        },
    )
