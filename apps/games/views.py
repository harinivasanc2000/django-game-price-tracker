import json
from django.shortcuts import render, get_object_or_404
from .models import Game, PriceRecord


def home(request):
    """Landing page with optional platform filter."""
    platform = request.GET.get("platform", "").strip().lower()
    games = Game.objects.filter(is_active=True)
    if platform and platform in dict(Game.Platform.choices):
        games = games.filter(platform=platform)
    games = games.order_by("title")

    platforms = Game.Platform.choices
    return render(
        request,
        "games/home.html",
        {
            "games": games,
            "platforms": platforms,
            "current_platform": platform,
        },
    )


def game_compare(request, slug):
    """Price comparison + history chart for a single game."""
    game = get_object_or_404(Game, slug=slug, is_active=True)

    all_prices = (
        PriceRecord.objects.filter(game=game)
        .select_related("store")
        .order_by("price", "-recorded_at")
    )

    seen = set()
    unique_prices = []
    for p in all_prices:
        if p.store_id not in seen:
            seen.add(p.store_id)
            unique_prices.append(p)

    lowest = unique_prices[0] if unique_prices else None

    history = list(
        PriceRecord.objects.filter(game=game)
        .select_related("store")
        .order_by("recorded_at")[:60]
    )

    change = None
    if len(history) >= 2:
        prev = history[-2]
        curr = history[-1]
        delta = curr.price - prev.price
        change = {
            "delta": delta,
            "pct": float((delta / prev.price) * 100) if prev.price else 0,
            "direction": "down" if delta < 0 else ("up" if delta > 0 else "same"),
            "from_price": prev.price,
            "to_price": curr.price,
            "currency": curr.currency,
        }

    chart_labels = json.dumps([h.recorded_at.strftime("%d %b %H:%M") for h in history])
    chart_values = json.dumps([float(h.price) for h in history])
    chart_stores = json.dumps([h.store.name for h in history])

    siblings = (
        Game.objects.filter(title__iexact=game.title, is_active=True)
        .exclude(pk=game.pk)
        .order_by("platform")
    )

    return render(
        request,
        "games/compare.html",
        {
            "game": game,
            "prices": unique_prices,
            "lowest": lowest,
            "history": history,
            "change": change,
            "chart_labels": chart_labels,
            "chart_values": chart_values,
            "chart_stores": chart_stores,
            "siblings": siblings,
            "platforms": Game.Platform.choices,
        },
    )
