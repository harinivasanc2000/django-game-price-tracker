import json
from django.shortcuts import render, get_object_or_404, redirect
from django.utils.text import slugify
from django.contrib import messages
from .models import Game, PriceRecord, Store, BrowseHistory
from .clients.steam import search_store, get_app_details


def _session_key(request):
    if not request.session.session_key:
        request.session.create()
    return request.session.session_key


def _log_history(request, action, query="", steam_app_id=None, title="", detail_url=""):
    BrowseHistory.objects.create(
        session_key=_session_key(request),
        action=action,
        query=query[:255],
        steam_app_id=steam_app_id,
        title=(title or "")[:255],
        detail_url=(detail_url or "")[:255],
    )


def home(request):
    platform = request.GET.get("platform", "").strip().lower()
    games = Game.objects.filter(is_active=True)
    if platform and platform in dict(Game.Platform.choices):
        games = games.filter(platform=platform)
    games = games.order_by("title")
    recent = BrowseHistory.objects.filter(session_key=_session_key(request))[:12]
    return render(
        request,
        "games/home.html",
        {
            "games": games,
            "platforms": Game.Platform.choices,
            "current_platform": platform,
            "recent": recent,
        },
    )


def steam_search(request):
    q = request.GET.get("q", "").strip()
    country = request.GET.get("cc", "GB").strip().upper() or "GB"
    results, error = [], None
    if q:
        _log_history(request, BrowseHistory.Action.SEARCH, query=q)
        results = search_store(q, country=country, limit=36)
        if not results:
            error = "No Steam results. Try full name (e.g. Cyberpunk 2077) or another spelling."
    return render(
        request,
        "games/steam_search.html",
        {"q": q, "results": results, "error": error, "country": country},
    )


def steam_detail(request, app_id: int):
    country = request.GET.get("cc", "GB").strip().upper() or "GB"
    detail = get_app_details(app_id, country=country)
    if not detail:
        messages.error(request, f"Could not load Steam app {app_id}.")
        return redirect("games:steam_search")
    _log_history(
        request,
        BrowseHistory.Action.VIEW,
        steam_app_id=app_id,
        title=detail["name"],
        detail_url=f"/steam/{app_id}/",
    )
    already = Game.objects.filter(steam_app_id=app_id, is_active=True).first()
    return render(
        request,
        "games/steam_detail.html",
        {"d": detail, "country": country, "already_tracked": already},
    )


def track_steam(request, app_id: int):
    country = request.GET.get("cc", "GB").strip().upper() or "GB"
    detail = get_app_details(app_id, country=country)
    if not detail:
        messages.error(request, f"Could not fetch Steam app {app_id}.")
        return redirect("games:steam_search")
    name = detail["name"]
    base_slug = slugify(f"{name}-pc")[:180] or f"steam-{app_id}"
    slug, n = base_slug, 1
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
            "store_type": Store.StoreType.OFFICIAL,
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
    _log_history(
        request,
        BrowseHistory.Action.TRACK,
        steam_app_id=app_id,
        title=name,
        detail_url=f"/game/{game.slug}/",
    )
    messages.success(request, f"Tracked {name}: {detail['price']} {detail['currency']}")
    return redirect("games:compare", slug=game.slug)


def history_page(request):
    items = BrowseHistory.objects.filter(session_key=_session_key(request))[:100]
    return render(request, "games/history.html", {"items": items})


def game_compare(request, slug):
    game = get_object_or_404(Game, slug=slug, is_active=True)
    all_prices = (
        PriceRecord.objects.filter(game=game)
        .select_related("store")
        .order_by("price", "-recorded_at")
    )
    seen, unique_prices = set(), []
    for p in all_prices:
        if p.store_id not in seen:
            seen.add(p.store_id)
            unique_prices.append(p)
    lowest = unique_prices[0] if unique_prices else None
    history = list(
        PriceRecord.objects.filter(game=game).select_related("store").order_by("recorded_at")
    )
    history_chart = history[-90:] if len(history) > 90 else history
    change = None
    if len(history) >= 2:
        prev, curr = history[-2], history[-1]
        delta = curr.price - prev.price
        change = {
            "delta": delta,
            "pct": float((delta / prev.price) * 100) if prev.price else 0,
            "direction": "down" if delta < 0 else ("up" if delta > 0 else "same"),
            "currency": curr.currency,
        }
    chart_labels = json.dumps([h.recorded_at.strftime("%d %b %H:%M") for h in history_chart])
    chart_values = json.dumps([float(h.price) for h in history_chart])
    chart_stores = json.dumps([h.store.name for h in history_chart])
    retail_baseline = None
    for h in reversed(history_chart):
        if h.original_price:
            retail_baseline = float(h.original_price)
            break
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
            "retail_baseline": retail_baseline,
            "siblings": siblings,
            "platforms": Game.Platform.choices,
        },
    )
