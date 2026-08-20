import json
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
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
from .clients.psn import search_psn
from .clients.amazon_uk import search_amazon_uk
from .clients.uk_stores import (
    uk_search_links,
    try_cex_search,
    try_ebay_uk,
    platform_query,
    fetch_uk_physical_bundle,
)
from .clients.news import steam_news, social_news_links

from .views_best_deals import best_deals  # noqa: F401,E402

POPULAR_APP_IDS = [
    1091500, 1245620, 271590, 1174180, 1593500, 1086940,
    292030, 1817070, 814380, 1113000, 108710, 1145360,
]

PLATFORMS = [
    ("", "All"),
    ("pc", "PC"),
    ("ps4", "PS4"),
    ("ps5", "PS5"),
    ("xbox", "Xbox"),
    ("switch", "Switch"),
]

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
    old_ids = list(
        BrowseHistory.objects.filter(session_key=skey).values_list("id", flat=True)[
            HISTORY_MAX_PER_SESSION:
        ]
    )
    if old_ids:
        BrowseHistory.objects.filter(id__in=old_ids).delete()
    recently_pruned = request.session.get("history_pruned_at")
    try:
        need_prune = (
            not recently_pruned
            or (timezone.now() - timezone.datetime.fromisoformat(recently_pruned)).total_seconds()
            > HISTORY_PRUNE_INTERVAL.total_seconds()
        )
    except Exception:
        need_prune = True
    if need_prune:
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


def _gbp_point(amount, currency="GBP") -> float | None:
    v = to_gbp(amount, currency)
    return float(v) if v is not None else None


def _collapse_changes(pairs: list[tuple[str, float]]) -> list[tuple[str, float]]:
    if not pairs:
        return []
    out = [pairs[0]]
    for lab, price in pairs[1:]:
        if abs(price - out[-1][1]) >= 0.005:
            out.append((lab, price))
    return out


def _build_chart_payload(already, detail, store_deals, launch, psn_rows, amazon_rows, cex_rows, ebay_rows):
    points: dict[str, list[tuple[str, float]]] = defaultdict(list)

    if already:
        history = list(
            PriceRecord.objects.filter(game=already)
            .select_related("store")
            .order_by("recorded_at")[:200]
        )
        for h in history:
            label = h.recorded_at.strftime("%d %b %H:%M")
            gbp = _gbp_point(h.price, h.currency)
            if gbp is not None:
                points[h.store.name].append((label, gbp))

    now = "Now"
    if detail.get("price") is not None and detail.get("price_status") == "paid":
        g = _gbp_point(detail["price"], detail.get("currency") or "GBP")
        if g is not None:
            points["Steam"].append((now, g))
    for deal in store_deals[:8]:
        g = _gbp_point(deal["price"], deal.get("currency") or "USD")
        if g is not None:
            points[deal["store_name"]].append((now, g))
    for row in psn_rows[:1]:
        if float(row.get("price") or 0) > 0:
            g = _gbp_point(row["price"], "GBP")
            if g is not None:
                points["PlayStation Store (UK)"].append((now, g))
    for row in amazon_rows[:1]:
        g = _gbp_point(row["price"], "GBP")
        if g is not None:
            points["Amazon UK"].append((now, g))
    for row in cex_rows[:1]:
        g = _gbp_point(row["price"], "GBP")
        if g is not None:
            points["CeX"].append((now, g))
    for row in ebay_rows[:1]:
        g = _gbp_point(row["price"], "GBP")
        if g is not None:
            points["eBay UK"].append((now, g))

    for seller in list(points.keys()):
        points[seller] = _collapse_changes(points[seller])

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
    avg_pairs = [(labels[i], avg[i]) for i in range(len(labels)) if avg[i] is not None]
    avg_collapsed = _collapse_changes(avg_pairs)
    if avg_collapsed:
        labels = [p[0] for p in avg_collapsed]
        avg = [p[1] for p in avg_collapsed]
        for seller in series:
            by_lab = {lab: price for lab, price in points.get(seller, [])}
            series[seller] = [by_lab.get(lab) for lab in labels]

    launch_series = [launch for _ in labels] if launch is not None else [None for _ in labels]
    sellers = sorted(series.keys(), key=lambda s: (s != "Steam", s.lower()))
    return {
        "labels": labels,
        "series": series,
        "average": avg,
        "launch": launch_series,
        "sellers": sellers,
        "unit": "GBP",
        "change_only": True,
    }


def _serialize_deal_row(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        if isinstance(v, Decimal):
            out[k] = float(v)
        else:
            out[k] = v
    return out


def _platform_bundle(title: str, platform: str = "") -> dict:
    platform = (platform or "").strip().lower()
    psn_query = platform_query(title, platform) if platform.startswith("ps") else title
    amz_extra = platform.upper() if platform else ""

    with ThreadPoolExecutor(max_workers=4) as pool:
        f_psn = pool.submit(search_psn, psn_query, 8)
        f_amz = pool.submit(search_amazon_uk, title, amz_extra, 6)
        f_uk = pool.submit(fetch_uk_physical_bundle, title, platform, 5)
        psn_rows = f_psn.result()
        amazon = f_amz.result()
        uk = f_uk.result()

    cex = uk.get("cex") or {}
    ebay = uk.get("ebay") or {}
    game = uk.get("game") or {}
    argos = uk.get("argos") or {}
    currys = uk.get("currys") or {}

    return {
        "platform": platform,
        "psn_rows": [_serialize_deal_row(r) for r in psn_rows],
        "amazon_rows": [_serialize_deal_row(r) for r in (amazon.get("results") or [])],
        "amazon_blocked": amazon.get("blocked", True),
        "amazon_search_url": amazon.get("search_url"),
        "cex_rows": [_serialize_deal_row(r) for r in (cex.get("results") or [])],
        "cex_blocked": cex.get("blocked", True),
        "cex_search_url": cex.get("search_url"),
        "ebay_rows": [_serialize_deal_row(r) for r in (ebay.get("results") or [])],
        "ebay_blocked": ebay.get("blocked", True),
        "ebay_search_url": ebay.get("search_url"),
        "game_rows": [_serialize_deal_row(r) for r in (game.get("results") or [])],
        "game_blocked": game.get("blocked", True),
        "game_search_url": game.get("search_url"),
        "argos_rows": [_serialize_deal_row(r) for r in (argos.get("results") or [])],
        "argos_blocked": argos.get("blocked", True),
        "argos_search_url": argos.get("search_url"),
        "currys_rows": [_serialize_deal_row(r) for r in (currys.get("results") or [])],
        "currys_blocked": currys.get("blocked", True),
        "currys_search_url": currys.get("search_url"),
        "uk_links": uk.get("uk_links") or uk_search_links(title, platform=platform),
    }


def platform_deals_api(request, app_id: int):
    platform = request.GET.get("platform", "").strip().lower()
    country = request.GET.get("cc", "GB").strip().upper() or "GB"
    detail = get_app_details(app_id, country=country)
    if not detail:
        return JsonResponse({"error": "not found"}, status=404)
    data = _platform_bundle(detail["name"], platform)
    return JsonResponse(data)


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

    with ThreadPoolExecutor(max_workers=6) as pool:
        f_deals = pool.submit(deals_for_title, detail["name"], 15)
        f_news = pool.submit(steam_news, app_id, 8)
        f_plat = pool.submit(_platform_bundle, detail["name"], platform)
        store_deals = f_deals.result()
        news_items = f_news.result()
        plat = f_plat.result()

    psn_rows = plat["psn_rows"]
    amazon_rows = plat["amazon_rows"]
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
        plat["cex_rows"],
        plat["ebay_rows"],
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
    for row in psn_rows:
        if float(row.get("price") or 0) > 0:
            live_offers.append(
                {
                    "store": "PSN UK",
                    "price": row["price"],
                    "price_gbp": to_gbp_or_zero(row["price"], "GBP"),
                    "currency": "GBP",
                    "kind": "official",
                    "url": row.get("url"),
                }
            )
            break
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
    for key, label, kind in (
        ("cex_rows", "CeX", "used"),
        ("ebay_rows", "eBay UK", "marketplace"),
        ("game_rows", "GAME UK", "retail"),
        ("argos_rows", "Argos", "retail"),
        ("currys_rows", "Currys", "retail"),
    ):
        rows = plat.get(key) or []
        if rows:
            live_offers.append(
                {
                    "store": label,
                    "price": rows[0]["price"],
                    "price_gbp": to_gbp_or_zero(rows[0]["price"], "GBP"),
                    "currency": "GBP",
                    "kind": kind,
                    "url": rows[0].get("url") or plat.get(key.replace("_rows", "_search_url")),
                }
            )
    if store_deals:
        live_offers.append(
            {
                "store": store_deals[0]["store_name"],
                "price": store_deals[0]["price"],
                "price_gbp": to_gbp_or_zero(
                    store_deals[0]["price"], store_deals[0].get("currency") or "USD"
                ),
                "currency": store_deals[0].get("currency") or "USD",
                "kind": "third-party",
                "url": store_deals[0].get("url"),
            }
        )
    live_offers.sort(key=lambda x: x["price_gbp"])

    watched = None
    if request.user.is_authenticated and already:
        watched = Watch.objects.filter(user=request.user, game=already).first()

    steam_os = detail.get("platforms") or []
    store_platforms = [("pc", "PC"), ("ps4", "PS4"), ("ps5", "PS5"), ("xbox", "Xbox"), ("switch", "Switch")]

    wallpaper = (
        detail.get("library_hero")
        or detail.get("page_background")
        or detail.get("header_image")
        or ""
    )

    savings_vs_launch = None
    if launch and live_offers:
        best_gbp = float(live_offers[0]["price_gbp"])
        if launch > 0:
            savings_vs_launch = int(round((1 - best_gbp / launch) * 100))

    return render(
        request,
        "games/steam_detail.html",
        {
            "d": detail,
            "country": country,
            "platforms": PLATFORMS,
            "store_platforms": store_platforms,
            "steam_os": steam_os,
            "current_platform": platform,
            "already_tracked": already,
            "catalog_game": catalog,
            "store_deals": store_deals,
            "psn_rows": psn_rows,
            "amazon_rows": amazon_rows,
            "amazon_blocked": plat.get("amazon_blocked", True),
            "amazon_search_url": plat.get("amazon_search_url"),
            "cex_rows": plat["cex_rows"],
            "cex_blocked": plat.get("cex_blocked", True),
            "cex_search_url": plat.get("cex_search_url"),
            "ebay_rows": plat["ebay_rows"],
            "ebay_blocked": plat.get("ebay_blocked", True),
            "ebay_search_url": plat.get("ebay_search_url"),
            "game_rows": plat.get("game_rows") or [],
            "game_blocked": plat.get("game_blocked", True),
            "game_search_url": plat.get("game_search_url"),
            "argos_rows": plat.get("argos_rows") or [],
            "argos_blocked": plat.get("argos_blocked", True),
            "argos_search_url": plat.get("argos_search_url"),
            "currys_rows": plat.get("currys_rows") or [],
            "currys_blocked": plat.get("currys_blocked", True),
            "currys_search_url": plat.get("currys_search_url"),
            "uk_links": plat["uk_links"],
            "news_items": news_items,
            "social_links": social_links,
            "live_offers": live_offers,
            "launch": launch,
            "launch_currency": launch_currency,
            "launch_source": launch_source,
            "savings_vs_launch": savings_vs_launch,
            "best_third_party": store_deals[0] if store_deals else None,
            "chart_json": json.dumps(chart),
            "has_chart": bool(chart["labels"]),
            "watched": watched,
            "is_watched": watched is not None,
            "game_wallpaper": wallpaper,
            "screenshots": detail.get("screenshots") or [],
            "wide_layout": True,
            "app_id": app_id,
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
    alerts = list(
        PriceAlert.objects.filter(watch__user=request.user)
        .select_related("watch__game")
        .order_by("-created_at")[:20]
    )
    unsent_alerts = sum(1 for a in alerts if not a.is_sent)
    return render(
        request,
        "games/profile.html",
        {
            "tracked": tracked,
            "watches": watches,
            "alerts": alerts,
            "unsent_alerts": unsent_alerts,
        },
    )


def game_compare(request, slug):
    game = get_object_or_404(Game, slug=slug, is_active=True)
    if game.steam_app_id:
        return redirect("games:steam_detail", app_id=game.steam_app_id)
    prices = list(
        PriceRecord.objects.filter(game=game)
        .select_related("store")
        .order_by("price", "-recorded_at")[:50]
    )

    def _gbp(p):
        return to_gbp_or_zero(p.price, p.currency)

    prices.sort(key=_gbp)
    lowest = prices[0] if prices else None
    return render(
        request,
        "games/compare.html",
        {
            "game": game,
            "prices": prices,
            "lowest": lowest,
            "change": None,
            "retail_baseline": float(game.launch_price) if game.launch_price else None,
            "siblings": [],
            "history_count": 0,
            "chart_labels": "[]",
            "chart_values": "[]",
            "chart_stores": "[]",
            "watched": None,
        },
    )


def _redirect_after_watch(game: Game):
    if game.steam_app_id:
        return redirect("games:steam_detail", app_id=game.steam_app_id)
    return redirect("games:compare", slug=game.slug)


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
            return _redirect_after_watch(game)
    Watch.objects.update_or_create(
        user=request.user,
        game=game,
        defaults={"target_price": target},
    )
    if target is None:
        messages.success(request, f"Watching {game.title}.")
    else:
        messages.success(request, f"Watching {game.title} — alert under £{target}.")
    return _redirect_after_watch(game)


@login_required
@require_POST
def unwatch_game(request, slug):
    game = get_object_or_404(Game, slug=slug, is_active=True)
    Watch.objects.filter(user=request.user, game=game).delete()
    messages.info(request, f"Stopped watching {game.title}.")
    return _redirect_after_watch(game)


@login_required
@require_POST
def clear_alerts(request):
    PriceAlert.objects.filter(watch__user=request.user, is_sent=False).update(
        is_sent=True, sent_at=timezone.now()
    )
    messages.info(request, "Price alerts marked as read.")
    return redirect("games:profile")
