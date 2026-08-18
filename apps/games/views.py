from django.shortcuts import render, get_object_or_404
from django.db.models import Min
from .models import Game, PriceRecord, Store


def home(request):
    """Simple landing page listing tracked games."""
    games = Game.objects.filter(is_active=True).order_by("title")
    return render(request, "games/home.html", {"games": games})


def game_compare(request, slug):
    """Attractive price comparison page for a single game."""
    game = get_object_or_404(Game, slug=slug, is_active=True)

    # Latest price per store (simple approach for pilot)
    prices = (
        PriceRecord.objects.filter(game=game)
        .select_related("store")
        .order_by("price", "-recorded_at")
    )

    # Group by store keeping the cheapest / most recent for display
    seen = set()
    unique_prices = []
    for p in prices:
        if p.store_id not in seen:
            seen.add(p.store_id)
            unique_prices.append(p)

    lowest = unique_prices[0] if unique_prices else None

    return render(
        request,
        "games/compare.html",
        {
            "game": game,
            "prices": unique_prices,
            "lowest": lowest,
        },
    )
