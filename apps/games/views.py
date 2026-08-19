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
from .clients.psn import search_psn, best_psn_deal
from .clients.amazon_uk import search_amazon_uk
from .clients.uk_stores import uk_search_links, try_cex_search, try_ebay_uk, platform_query
from .clients.news import steam_news, social_news_links

POPULAR_APP_IDS = [
    1091500, 1245620, 271590, 1174180, 1593500, 1086940,
    292030, 1817070, 814380, 1113000, 108710, 1145360,
]

PLATFORMS = [
    ("", "All platforms"),
    ("pc", "PC"),
    ("ps4", "PS4"),
    ("ps5", "PS5"),
    ("xbox", "Xbox"),
    ("switch", "Switch"),
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


def _build_chart_payload(already, detail, store_deals, launch, psn_rows, amazon_rows, cex_rows, ebay_rows):
    current = float(detail["price"]) if detail.get("price") is not None else None
    points: dict[str, list[tuple[str, float]]] = defaultdict(list)

    if already:
        history = list(
            PriceRecord.objects.filter(game=already)
            .select_related("store")
            .order_by("recorded_at")[:150]
        )
        for h in history:
            label = h.recorded_at.strftime("%d %b %H:%M")
            points[h.store.name].append((label, float(h.price)))

    now = "Now"
    if current is not None and detail.get("price_status") == "paid":
        points["Steam"].append((now, current))
    for deal in store_deals[:8]:
        points[deal["store_name"]].append((now, float(deal["price"])))
    for row in psn_rows[:1]:
        if float(row.get("price") or 0) > 0:
            points["PlayStation Store (UK)"].append((now, float(row["price"])))
    for row in amazon_rows[:1]:
        points["Amazon UK"].append((now, float(row["price"])))
    for row in cex_rows[:1]:
        points["CeX"].append((now, float(row["price"])))
    for row in ebay_rows[:1]:
        points["eBay UK"].append((now, float(row["price"])))

    labels: list[str] = []
    seen = set()
    for pairs in points.values():
        for lab, _ in pairs:
            if lab not in seen:
                seen.add(lab)
                labels.append(lab)
    if not labels:
        labels = ["Now"]

    series: dict[str, list] = {}
    for seller, pairs in points.items():
        by_lab = {lab: price for lab, price in pairs}
        series[seller] = [by_lab.get(lab) for lab in labels]

    avg = []
    for i, _ in enumerate(labels):
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
    platform = request.GET.get("platform", "").strip().lower()
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
        {
            "tracked_home": tracked,
            "popular": popular,
            "platforms": PLATFORMS,
            "current_platform": platform,
        },
    )


def steam_search(request):
    q = request.GET.get("q", "").strip()
    country = request.GET.get("cc", "GB").strip().upper() or "GB"
    platform = request.GET.get("platform", "").strip().lower()
    results, error = [], None
    if q:
        _log_history(request, BrowseHistory.Action.SEARCH, query=q)
        # Platform hint in Steam query improves ranking slightly
        search_q = platform_query(q, platform) if platform else q
        results = search_store(search_q, country=country, limit=40)
        if not results:
            error = "No close matches. Try another spelling or a fuller title."
    return render(
        request,
        "games/steam_search.html",
        {
            "q": q,
            "results": results,
            "error": error,
            "country": country,
            "platforms": PLATFORMS,
            "current_platform": platform,
        },
    )


def steam_suggest(request):
    q = request.GET.get("q", "").strip()
    country = request.GET.get("cc", "GB").strip().upper() or "GB"
    if len(q) < 2:
        return JsonResponse({"suggestions": []})
    return JsonResponse({"suggestions": suggest_store(q, country=country, limit=8)})


def steam_detail(request, app_id: int):
    country = request.GET.get("cc", "GB").strip().upper() or "GB"
    platform = request.GET.get("platform", "").strip().lower()
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
    store_deals = deals_for_title(detail["name"], limit=15)

    # Platform-aware queries for console / physical
    psn_q = platform_query(detail["name"], platform or "ps5")
    psn_rows = search_psn(psn_q if platform.startswith("ps") else detail["name"], limit=8)
    amazon = search_amazon_uk(detail["name"], extra=platform.upper() if platform else "", limit=6)
    amazon_rows = amazon.get("results") or []

    cex = try_cex_search(detail["name"], platform=platform, limit=6)
    ebay = try_ebay_uk(detail["name"], platform=platform, limit=6)
    uk_links = uk_search_links(detail["name"], platform=platform)

    news_items = steam_news(app_id, count=5)
    social_links = social_news_links(detail["name"])

    launch = float(catalog.launch_price) if catalog and catalog.launch_price else None
    launch_currency = (catalog.launch_currency if catalog else None) or "GBP"
    launch_source = (catalog.launch_price_source if catalog else "") or ""

    chart = _build_chart_payload(
        already,
        detail,
        store_deals,
        launch,
        psn_rows,
        amazon_rows,
        cex.get("results") or [],
        ebay.get("results") or [],
    )

    live_offers = []
    if detail.get("price_status") == "paid" and detail.get("price") is not None:
        live_offers.append(
            {
                "store": "Steam",
                "price": detail["price"],
                "currency": detail.get("currency") or "GBP",
                "kind": "official",
                "url": detail.get("url"),
            }
        )
    best_psn = best_psn_deal(detail["name"])
    if best_psn and float(best_psn.get("price") or 0) > 0:
        live_offers.append(
            {
                "store": "PSN UK",
                "price": best_psn["price"],
                "currency": "GBP",
                "kind": "official",
                "url": best_psn.get("url"),
            }
        )
    if amazon_rows:
        live_offers.append(
            {
                "store": "Amazon UK",
                "price": amazon_rows[0]["price"],
                "currency": "GBP",
                "kind": "marketplace",
                "url": amazon_rows[0].get("url"),
            }
        )
    if cex.get("results"):
        live_offers.append(
            {
                "store": "CeX",
                "price": cex["results"][0]["price"],
                "currency": "GBP",
                "kind": "used",
                "url": cex.get("search_url"),
            }
        )
    if ebay.get("results"):
        live_offers.append(
            {
                "store": "eBay UK",
                "price": ebay["results"][0]["price"],
                "currency": "GBP",
                "kind": "marketplace",
                "url": ebay["results"][0].get("url"),
            }
        )
    if store_deals:
        live_offers.append(
            {
                "store": store_deals[0]["store_name"],
                "price": store_deals[0]["price"],
                "currency": store_deals[0].get("currency") or "USD",
                "kind": "third-party",
                "url": store_deals[0].get("url"),
            }
        )
    live_offers.sort(key=lambda x: float(x["price"]))

    return render(
        request,
        "games/steam_detail.html",
        {
            "d": detail,
            "country": country,
            "platforms": PLATFORMS,
            "current_platform": platform,
            "already_tracked": already,
            "catalog_game": catalog,
            "store_deals": store_deals,
            "psn_rows": psn_rows,
            "amazon_rows": amazon_rows,
            "amazon_blocked": amazon.get("blocked", True),
            "amazon_search_url": amazon.get("search_url"),
            "cex_rows": cex.get("results") or [],
            "cex_blocked": cex.get("blocked", True),
            "cex_search_url": cex.get("search_url"),
            "ebay_rows": ebay.get("results") or [],
            "ebay_blocked": ebay.get("blocked", True),
            "ebay_search_url": ebay.get("search_url"),
            "uk_links": uk_links,
            "news_items": news_items,
            "social_links": social_links,
            "live_offers": live_offers,
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
