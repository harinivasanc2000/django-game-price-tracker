from django.shortcuts import render, get_object_or_404
from django.db.models import Min
from .models import Game, PriceRecord, Store


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

    # Current best per store
    seen = set()
    unique_prices = []
    for p in all_prices:
        if p.store_id not in seen:
            seen.add(p.store_id)
            unique_prices.append(p)

    lowest = unique_prices[0] if unique_prices else None

    # History for chart (oldest first, last 60 points)
    history_qs = (
        PriceRecord.objects.filter(game=game)
        .select_related("store")
        .order_by("recorded_at")[:60]
    )
    history = list(history_qs)

    # Price change vs previous record (same store if possible)
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

    # Chart.js data
    chart_labels = [h.recorded_at.strftime("%d %b %H:%M") for h in history]
    chart_values = [float(h.price) for h in history]
    chart_stores = [h.store.name for h in history]

    # Sibling platforms (same title, other platforms)
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
