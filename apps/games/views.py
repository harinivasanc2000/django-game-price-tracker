import json
from django.shortcuts import render, get_object_or_404, redirect
from django.utils.text import slugify
from django.contrib import messages
from .models import Game, PriceRecord, Store
from .clients.steam import search_store, get_app_price


def home(request):
    """Landing page: search bar + platform filter + tracked games."""
    platform = request.GET.get("platform", "").strip().lower()
    q = request.GET.get("q", "").strip()

    games = Game.objects.filter(is_active=True)
    if platform and platform in dict(Game.Platform.choices):
        games = games.filter(platform=platform)
    if q:
        games = games.filter(title__icontains=q)
    games = games.order_by("title")

    return render(
        request,
        "games/home.html",
        {
            "games": games,
            "platforms": Game.Platform.choices,
            "current_platform": platform,
            "q": q,
        },
    )


def steam_search(request):
    """
    Search Steam by keyword (any game).
    Broad query → many titles + editions with thumbnails.
    Narrow query → fewer, more specific hits.
    """
    q = request.GET.get("q", "").strip()
    country = request.GET.get("cc", "GB").strip().upper() or "GB"
    results = []
    error = None

    if q:
        results = search_store(q, country=country, limit=30)
        if not results:
            error = "No Steam results (or request failed). Try a different spelling."

    return render(
        request,
        "games/steam_search.html",
        {
            "q": q,
            "results": results,
            "error": error,
            "country": country,
        },
    )


def track_steam(request, app_id: int):
    """Fetch live Steam price, save Game + PriceRecord, go to compare page."""
    country = request.GET.get("cc", "GB").strip().upper() or "GB"
    detail = get_app_price(app_id, country=country)

    if not detail:
        messages.error(request, f"Could not fetch Steam app {app_id}.")
        return redirect("games:steam_search")

    name = detail["name"]
    base_slug = slugify(f"{name}-pc")[:180] or f"steam-{app_id}"
    slug = base_slug
    n = 1
    while Game.objects.filter(slug=slug).exclude(steam_app_id=app_id).exists():
        slug = f"{base_slug}-{n}"
        n += 1

    game, _ = Game.objects.update_or_create(
        steam_app_id=app_id,
        defaults={
            "title": name[:255],
            "slug": slug,
            "platform": Game.Platform.PC,
            "cover_url": detail.get("header_image") or "",
            "is_active": True,
        },
    )

    store, _ = Store.objects.get_or_create(
        slug="steam",
        defaults={
            "name": "Steam",
            "website": "https://store.steampowered.com",
            "store_type": Store.StoreType.PHYSICAL if False else Store.StoreType.OFFICIAL,
            "country": "GB",
            "notes": "Official PC digital store",
        },
    )

    PriceRecord.objects.create(
        game=game,
        store=store,
        price=detail["price"],
        currency=detail["currency"],
        original_price=detail.get("original"),
        discount_percent=detail.get("discount") or None,
        url=detail["url"],
        is_physical=False,
        is_used=False,
        in_stock=True,
        notes=name[:255],
    )

    messages.success(
        request,
        f"Tracked {name}: {detail['price']} {detail['currency']}",
    )
    return redirect("games:compare", slug=game.slug)


def game_compare(request, slug):
    """Price comparison + history chart."""
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
        .order_by("recorded_at")
    )
    history_chart = history[-90:] if len(history) > 90 else history

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

    chart_labels = json.dumps([h.recorded_at.strftime("%d %b %H:%M") for h in history_chart])
    chart_values = json.dumps([float(h.price) for h in history_chart])
    chart_stores = json.dumps([h.store.name for h in history_chart])

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
            "history_count": len(history),
            "change": change,
            "chart_labels": chart_labels,
            "chart_values": chart_values,
            "chart_stores": chart_stores,
            "siblings": siblings,
            "platforms": Game.Platform.choices,
        },
    )
