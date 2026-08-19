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
from .clients.cheapshark import deals_for_title

POPULAR_APP_IDS = [
    1091500, 1245620, 271590, 1174180, 1593500, 1086940,
    292030, 1817070, 814380, 1113000, 108710, 1145360,
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


def _unique_slug(name: str, app_id: int) -> str:
    base = slugify(f"{name}-pc")[:160] or f"steam-{app_id}"
    slug, n = base, 1
    while Game.objects.filter(slug=slug).exclude(steam_app_id=app_id).exists():
        slug = f"{base}-{app_id}" if n == 1 else f"{base}-{n}"
        n += 1
        if n > 50:
            slug = f"steam-{app_id}"
            break
    return slug[:180]


def home(request):
    list(messages.get_messages(request))
    tracked = list(Game.objects.filter(is_active=True).order_by("title")[:12])
    tracked_ids = {g.steam_app_id for g in tracked if g.steam_app_id}
    popular = list(
        Game.objects.filter(steam_app_id__in=POPULAR_APP_IDS)
        .exclude(steam_app_id__in=tracked_ids)
    )
    order = {aid: i for i, aid in enumerate(POPULAR_APP_IDS)}
    popular.sort(key=lambda g: order.get(g.steam_app_id, 999))
    return render(
        request,
        "games/home.html",
        {"tracked_home": tracked, "popular": popular},
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
    """Full title page on click — prices, multi-store, launch vs current (no track required)."""
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

    # Multi-store deals (CheapShark public API — USD)
    store_deals = deals_for_title(detail["name"], limit=18)

    # Snapshot history if already tracked
    history = []
    if already:
        history = list(
            PriceRecord.objects.filter(game=already)
            .select_related("store")
            .order_by("recorded_at")[:90]
        )

    launch = None
    launch_currency = "GBP"
    launch_source = ""
    if catalog and catalog.launch_price:
        launch = float(catalog.launch_price)
        launch_currency = catalog.launch_currency or "GBP"
        launch_source = catalog.launch_price_source or ""

    current = float(detail["price"]) if detail.get("price") is not None else None
    list_price = float(detail["original"]) if detail.get("original") is not None else None

    # Simple 2-point chart: launch (if any) vs current Steam
    chart_labels = []
    chart_values = []
    if launch is not None:
        chart_labels.append("Launch ref")
        chart_values.append(launch)
    if list_price is not None and detail.get("price_status") == "paid":
        chart_labels.append("Steam list")
        chart_values.append(list_price)
    if current is not None and detail.get("price_status") == "paid":
        chart_labels.append("Steam now")
        chart_values.append(current)
    if history:
        chart_labels = [h.recorded_at.strftime("%d %b") for h in history]
        chart_values = [float(h.price) for h in history]

    return render(
        request,
        "games/steam_detail.html",
        {
            "d": detail,
            "country": country,
            "already_tracked": already,
            "catalog_game": catalog,
            "store_deals": store_deals,
            "launch": launch,
            "launch_currency": launch_currency,
            "launch_source": launch_source,
            "chart_labels": json.dumps(chart_labels),
            "chart_values": json.dumps(chart_values),
            "history_count": len(history),
        },
    )


def track_steam(request, app_id: int):
    """Track only — stay on detail page."""
    country = request.GET.get("cc", "GB").strip().upper() or "GB"
    detail = get_app_details(app_id, country=country)
    if not detail:
        return redirect("games:steam_search")

    name = detail["name"]
    slug = _unique_slug(name, app_id)
    existing = Game.objects.filter(steam_app_id=app_id).first()
    defaults = {
        "title": name[:255],
        "slug": existing.slug if existing else slug,
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
        },
    )

    status = detail.get("price_status") or "unknown"
    if status == "unknown" or detail.get("price") is None:
        price, original, discount = Decimal("0.00"), None, None
        notes = f"{name[:200]} [price unknown]"
    else:
        price = detail["price"] or Decimal("0.00")
        original = detail.get("original") or detail.get("list_price")
        discount = detail.get("discount") or None
        notes = name[:255]

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
        detail_url=f"/steam/{app_id}/",
    )
    return redirect("games:steam_detail", app_id=app_id)


@require_POST
def untrack_game(request, slug):
    game = get_object_or_404(Game, slug=slug)
    app_id = game.steam_app_id
    game.is_active = False
    game.save(update_fields=["is_active", "updated_at"])
    if app_id:
        return redirect("games:steam_detail", app_id=app_id)
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
    if game.steam_app_id:
        return redirect("games:steam_detail", app_id=game.steam_app_id)

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
    return render(
        request,
        "games/compare.html",
        {
            "game": game,
            "prices": unique_prices,
            "lowest": lowest,
            "history": history,
            "history_count": len(history),
            "change": None,
            "chart_labels": "[]",
            "chart_values": "[]",
            "chart_stores": "[]",
            "retail_baseline": float(game.launch_price) if game.launch_price else None,
            "baseline_label": "Launch",
            "siblings": [],
            "platforms": Game.Platform.choices,
        },
    )
