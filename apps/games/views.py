import json
from decimal import Decimal
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.utils.text import slugify
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from .models import Game, PriceRecord, Store, BrowseHistory
from .clients.steam import search_store, get_app_details, suggest_store

# Well-known titles for "Popular" (steam app ids from seed_launch_prices)
POPULAR_APP_IDS = [
    1091500,  # Cyberpunk 2077
    1245620,  # ELDEN RING
    271590,   # GTA V
    1174180,  # RDR2
    1593500,  # God of War
    1086940,  # Baldur's Gate 3
    292030,   # Witcher 3
    1817070,  # Spider-Man
    814380,   # Sekiro
    1113000,  # Persona 5 Royal
    108710,   # Yakuza Kiwami
    1145360,  # Hades
]


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
    # Consume any leftover flash messages so they never show on home
    list(messages.get_messages(request))

    tracked = list(Game.objects.filter(is_active=True).order_by("title")[:12])
    tracked_ids = {g.steam_app_id for g in tracked if g.steam_app_id}

    popular = list(
        Game.objects.filter(steam_app_id__in=POPULAR_APP_IDS)
        .exclude(steam_app_id__in=tracked_ids)
        .order_by("title")
    )
    # Keep popular order roughly as POPULAR_APP_IDS
    order = {aid: i for i, aid in enumerate(POPULAR_APP_IDS)}
    popular.sort(key=lambda g: order.get(g.steam_app_id, 999))

    return render(
        request,
        "games/home.html",
        {
            "tracked_home": tracked,
            "popular": popular,
        },
    )


def steam_search(request):
    q = request.GET.get("q", "").strip()
    country = request.GET.get("cc", "GB").strip().upper() or "GB"
    results, error = [], None
    if q:
        _log_history(request, BrowseHistory.Action.SEARCH, query=q)
        results = search_store(q, country=country, limit=40)
        if not results:
            error = "No close matches. Try another spelling or a fuller title."
    return render(
        request,
        "games/steam_search.html",
        {"q": q, "results": results, "error": error, "country": country},
    )


def steam_suggest(request):
    q = request.GET.get("q", "").strip()
    country = request.GET.get("cc", "GB").strip().upper() or "GB"
    if len(q) < 2:
        return JsonResponse({"suggestions": []})
    return JsonResponse({"suggestions": suggest_store(q, country=country, limit=8)})


def steam_detail(request, app_id: int):
    country = request.GET.get("cc", "GB").strip().upper() or "GB"
    detail = get_app_details(app_id, country=country)
    if not detail:
        return redirect("games:steam_search")
    _log_history(
        request,
        BrowseHistory.Action.VIEW,
        steam_app_id=app_id,
        title=detail["name"],
        detail_url=f"/steam/{app_id}/",
    )
    already = Game.objects.filter(steam_app_id=app_id, is_active=True).first()
    catalog = Game.objects.filter(steam_app_id=app_id).first()
    return render(
        request,
        "games/steam_detail.html",
        {
            "d": detail,
            "country": country,
            "already_tracked": already,
            "catalog_game": catalog,
        },
    )


def track_steam(request, app_id: int):
    country = request.GET.get("cc", "GB").strip().upper() or "GB"
    detail = get_app_details(app_id, country=country)
    if not detail:
        return redirect("games:steam_search")

    name = detail["name"]
    base_slug = slugify(f"{name}-pc")[:180] or f"steam-{app_id}"
    slug, n = base_slug, 1
    while Game.objects.filter(slug=slug).exclude(steam_app_id=app_id).exists():
        slug = f"{base_slug}-{n}"
        n += 1

    existing = Game.objects.filter(steam_app_id=app_id).first()
    defaults = {
        "title": name[:255],
        "slug": slug,
        "platform": Game.Platform.PC,
        "cover_url": detail.get("header_image") or "",
        "is_active": True,
    }
    if existing and existing.launch_price:
        defaults["launch_price"] = existing.launch_price
        defaults["launch_currency"] = existing.launch_currency
        defaults["launch_price_source"] = existing.launch_price_source

    game, _ = Game.objects.update_or_create(steam_app_id=app_id, defaults=defaults)

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

    status = detail.get("price_status") or "unknown"
    if status == "unknown" or detail.get("price") is None:
        price = Decimal("0.00")
        original = None
        discount = None
        notes = f"{name[:200]} [price unknown]"
    else:
        price = detail["price"] or Decimal("0.00")
        original = detail.get("original") or detail.get("list_price")
        discount = detail.get("discount") or None
        notes = name[:255]

    # No flash messages — silent track, go to compare page
    PriceRecord.objects.create(
        game=game,
        store=store,
        price=price,
        currency=detail.get("currency") or "GBP",
        original_price=original,
        discount_percent=discount,
        url=detail.get("url") or "",
        is_physical=False,
        is_used=False,
        in_stock=True,
        notes=notes,
    )

    _log_history(
        request,
        BrowseHistory.Action.TRACK,
        steam_app_id=app_id,
        title=name,
        detail_url=f"/game/{game.slug}/",
    )
    return redirect("games:compare", slug=game.slug)


@require_POST
def untrack_game(request, slug):
    game = get_object_or_404(Game, slug=slug)
    game.is_active = False
    game.save(update_fields=["is_active", "updated_at"])
    # Silent — no flash message on home
    return redirect("games:home")


def history_page(request):
    items = BrowseHistory.objects.filter(session_key=_session_key(request))[:100]
    return render(request, "games/history.html", {"items": items})


@login_required
def profile(request):
    return render(
        request,
        "games/profile.html",
        {"tracked": Game.objects.filter(is_active=True).order_by("title")[:50]},
    )


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
    baseline_label = "Retail baseline"
    if game.launch_price:
        retail_baseline = float(game.launch_price)
        baseline_label = "Launch / MSRP reference"
    else:
        for h in reversed(history_chart):
            if h.original_price and h.original_price > 0:
                retail_baseline = float(h.original_price)
                baseline_label = "Steam list price"
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
            "baseline_label": baseline_label,
            "siblings": siblings,
            "platforms": Game.Platform.choices,
        },
    )
