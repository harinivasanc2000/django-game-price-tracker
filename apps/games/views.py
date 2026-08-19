import json
from collections import defaultdict
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
from .clients.external_stores import external_links_for_title, ensure_uk_stores

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


def _build_chart_payload(already, detail, store_deals, launch):
    """
    Per-seller time series + average + launch.
    series: { "Steam": [..], "Humble Store": [..], ... }
    labels aligned across all series (nulls for gaps).
    """
    current = float(detail["price"]) if detail.get("price") is not None else None
    # seller -> list of (label, price)
    points: dict[str, list[tuple[str, float]]] = defaultdict(list)

    if already:
        history = list(
            PriceRecord.objects.filter(game=already)
            .select_related("store")
            .order_by("recorded_at")[:150]
        )
        for h in history:
            label = h.recorded_at.strftime("%d %b %H:%M")
            name = h.store.name
            points[name].append((label, float(h.price)))

    # Live "Now" points
    now = "Now"
    if current is not None and detail.get("price_status") == "paid":
        points["Steam"].append((now, current))
    for deal in store_deals[:12]:
        points[deal["store_name"]].append((now, float(deal["price"])))

    # Union of time labels in order of first appearance
    labels: list[str] = []
    seen = set()
    for pairs in points.values():
        for lab, _ in pairs:
            if lab not in seen:
                seen.add(lab)
                labels.append(lab)
    if not labels:
        labels = ["Now"]

    # Map label -> price per seller (last wins)
    series: dict[str, list] = {}
    for seller, pairs in points.items():
        by_lab = {}
        for lab, price in pairs:
            by_lab[lab] = price
        series[seller] = [by_lab.get(lab) for lab in labels]

    # Time-wise average across sellers that have a value at that label
    avg = []
    for i, _lab in enumerate(labels):
        vals = [series[s][i] for s in series if series[s][i] is not None]
        avg.append(round(sum(vals) / len(vals), 2) if vals else None)

    launch_series = [launch for _ in labels] if launch is not None else [None for _ in labels]

    sellers = sorted(series.keys(), key=lambda s: (s != "Steam", s.lower()))
    return {
        "labels": labels,
        "series": series,
        "average": avg,
        "launch": launch_series,
        "sellers": sellers,
    }


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

    ensure_uk_stores()
    already = Game.objects.filter(steam_app_id=app_id, is_active=True).first()
    catalog = Game.objects.filter(steam_app_id=app_id).first()
    store_deals = deals_for_title(detail["name"], limit=18)

    launch = float(catalog.launch_price) if catalog and catalog.launch_price else None
    launch_currency = (catalog.launch_currency if catalog else None) or "GBP"
    launch_source = (catalog.launch_price_source if catalog else "") or ""

    chart = _build_chart_payload(already, detail, store_deals, launch)
    external = external_links_for_title(detail["name"])

    return render(
        request,
        "games/steam_detail.html",
        {
            "d": detail,
            "country": country,
            "already_tracked": already,
            "catalog_game": catalog,
            "store_deals": store_deals,
            "external_links": external,
            "launch": launch,
            "launch_currency": launch_currency,
            "launch_source": launch_source,
            "best_third_party": store_deals[0] if store_deals else None,
            "chart_json": json.dumps(chart),
            "has_chart": bool(chart["labels"]),
        },
    )


def track_steam(request, app_id: int):
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
    ensure_uk_stores()

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

    try:
        from .tasks import refresh_one_game

        refresh_one_game(game, country=country)
    except Exception:
        pass

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
    return redirect("games:home")
