import json
from collections import defaultdict
from decimal import Decimal
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.utils.text import slugify
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.utils import timezone
from .models import (
    Game,
    PriceRecord,
    Store,
    BrowseHistory,
    Watch,
    PriceAlert,
)
from .fx import to_gbp, to_gbp_or_zero
from .clients.steam import search_store, get_app_details, suggest_store
from .clients.cheapshark import deals_for_title
from .clients.external_stores import ensure_uk_stores
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

# History: keep per-session list bounded and prune occasionally.
HISTORY_MAX_PER_SESSION = 100
HISTORY_PRUNE_INTERVAL = timezone.timedelta(hours=24)
HISTORY_PRUNE_MARK = timezone.timedelta(days=60)


def _session_key(request):
    if not request.session.session_key:
        request.session.create()
    return request.session.session_key


def _log_history(request, action, query="", steam_app_id=None, title="", detail_url=""):
    skey = _session_key(request)
    BrowseHistory.objects.create(
        session_key=skey,
        action=action,
        query=query[:255],
        steam_app_id=steam_app_id,
        title=(title or "")[:255],
        detail_url=(detail_url or "")[:255],
    )
    # Keep this session's history bounded and the table from growing forever.
    old_ids = BrowseHistory.objects.filter(session_key=skey).values_list("id", flat=True)[HISTORY_MAX_PER_SESSION:]
    if old_ids:
        BrowseHistory.objects.filter(id__in=list(old_ids)).delete()
    recently_pruned = request.session.get("history_pruned_at")
    if not recently_pruned or (timezone.now() - timezone.datetime.fromisoformat(recently_pruned)).total_seconds() > HISTORY_PRUNE_INTERVAL.total_seconds():
        BrowseHistory.objects.filter(created_at__lt=timezone.now() - HISTORY_PRUNE_MARK).delete()
        request.session["history_pruned_at"] = timezone.now().isoformat()


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


def _snapshot_since(game: Game, hours: int = 24) -> list:
    """Most recent snapshots (oldest first) within the window, for the change badge."""
    since = timezone.now() - timezone.timedelta(hours=hours)
    return list(
        PriceRecord.objects.filter(game=game, recorded_at__gte=since)
        .select_related("store")
        .order_by("recorded_at")[:12]
    )


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
                "price_gbp": to_gbp_or_zero(detail["price"], detail.get("currency") or "GBP"),
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
                "price_gbp": to_gbp_or_zero(best_psn["price"], "GBP"),
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
                "price_gbp": to_gbp_or_zero(amazon_rows[0]["price"], "GBP"),
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
                "price_gbp": to_gbp_or_zero(cex["results"][0]["price"], "GBP"),
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
                "price_gbp": to_gbp_or_zero(ebay["results"][0]["price"], "GBP"),
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
                "price_gbp": to_gbp_or_zero(store_deals[0]["price"], store_deals[0].get("currency") or "USD"),
                "currency": store_deals[0].get("currency") or "USD",
                "kind": "third-party",
                "url": store_deals[0].get("url"),
            }
        )
    # Sort by normalised GBP so USD key-shop prices compare fairly with UK retail.
    live_offers.sort(key=lambda x: x["price_gbp"])

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
            "is_watched": Watch.objects.filter(user=request.user, game_id=already.id).exists()
            if request.user.is_authenticated and already else False,
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

    # Refresh the rest of the sellers in the background; never block the
    # request on network calls. Eager Celery means it runs inline when
    # no broker is configured, so this also works out-of-the-box.
    try:
        from .tasks import refresh_single_game

        refresh_single_game.delay(game.id, country=country)
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
    watches = list(
        Watch.objects.filter(user=request.user).select_related("game").order_by("-created_at")
    )
    tracked = list(Game.objects.filter(is_active=True).order_by("title")[:50])
    unsent_alerts = PriceAlert.objects.filter(watch__user=request.user, is_sent=False).count()
    return render(
        request,
        "games/profile.html",
        {
            "tracked": tracked,
            "watches": watches,
            "unsent_alerts": unsent_alerts,
        },
    )


def game_compare(request, slug):
    game = get_object_or_404(Game, slug=slug, is_active=True)
    prices = list(
        PriceRecord.objects.filter(game=game)
        .select_related("store")
        .order_by("price", "-recorded_at")[:50]
    )
    # Normalise to GBP for a fair "lowest" comparison across currencies.
    def _gbp(p):
        return to_gbp_or_zero(p.price, p.currency)

    prices.sort(key=_gbp)
    lowest = prices[0] if prices else None

    # Latest snapshot per store (most recent row), for the change badge.
    recent = _snapshot_since(game, hours=24)
    change = None
    if len(recent) >= 2:
        first, last = recent[0], recent[-1]
        prev_gbp, cur_gbp = to_gbp_or_zero(first.price, first.currency), _gbp(last)
        if prev_gbp != cur_gbp:
            change = {
                "direction": "down" if cur_gbp < prev_gbp else "up",
                "delta": abs(cur_gbp - prev_gbp),
                "pct": abs((cur_gbp - prev_gbp) / prev_gbp * 100) if prev_gbp else 0,
                "currency": settings.DEFAULT_CURRENCY,
            }

    history = list(
        PriceRecord.objects.filter(game=game).select_related("store").order_by("recorded_at")[:150]
    )
    # Only keep one point per store per day to keep the chart light.
    chart_labels, chart_values, chart_stores, seen_days = [], [], [], set()
    for h in history:
        day = h.recorded_at.strftime("%Y-%m-%d")
        key = (h.store_id, day)
        if key in seen_days:
            continue
        seen_days.add(key)
        chart_labels.append(h.recorded_at.strftime("%d %b %y"))
        chart_values.append(float(h.price))
        chart_stores.append(h.store.name)

    siblings = Game.objects.filter(title=game.title, is_active=True).exclude(pk=game.pk)[:6]
    watched = (
        Watch.objects.filter(user=request.user, game=game).first()
        if request.user.is_authenticated else None
    )

    return render(
        request,
        "games/compare.html",
        {
            "game": game,
            "prices": prices,
            "lowest": lowest,
            "change": change,
            "retail_baseline": lowest.original_price if lowest else None,
            "siblings": siblings,
            "history_count": len(history),
            "chart_labels": json.dumps(chart_labels),
            "chart_values": json.dumps(chart_values),
            "chart_stores": json.dumps(chart_stores),
            "watched": watched,
        },
    )


@login_required
@require_POST
def watch_game(request, slug):
    game = get_object_or_404(Game, slug=slug, is_active=True)
    target_raw = (request.POST.get("target_price") or "").strip()
    target = None
    if target_raw:
        try:
            target = Decimal(target_raw)
            if target < 0:
                raise ValueError
        except Exception:
            messages.error(request, "Target price must be a positive number.")
            return redirect("games:compare", slug=slug)
    Watch.objects.update_or_create(
        user=request.user,
        game=game,
        defaults={"target_price": target},
    )
    messages.success(request, (
        f"Watching {game.title}."
        if target is None else
        f"Watching {game.title} — we'll alert you under £{target}."
    ))
    return redirect("games:compare", slug=slug)


@login_required
@require_POST
def unwatch_game(request, slug):
    game = get_object_or_404(Game, slug=slug, is_active=True)
    Watch.objects.filter(user=request.user, game=game).delete()
    messages.info(request, f"Stopped watching {game.title}.")
    return redirect("games:compare", slug=slug)


@login_required
@require_POST
def clear_alerts(request):
    """Mark all unsent alerts for this user as read/dismissed."""
    PriceAlert.objects.filter(watch__user=request.user, is_sent=False).update(is_sent=True, sent_at=timezone.now())
    messages.info(request, "Price alerts marked as read.")
    return redirect("games:profile")
