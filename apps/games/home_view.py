"""
Home page — popular grid + public Steam specials.
Tracked list stays in the side drawer (not on the main screen).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

from django.contrib import messages
from django.core.cache import cache
from django.db.models import Count, Max, OuterRef, Q, Subquery
from django.shortcuts import render
from django.utils import timezone

from .clients.public_deals import steam_featured
from .clients.steam import get_app_details
from .constants import POPULAR_APP_IDS
from .fx import to_gbp_or_zero
from .models import Game, PriceRecord

HOME_CACHE_KEY = "home:cards:v2"
HOME_CACHE_TTL = 180  # 3 minutes — balances freshness vs Steam rate limits
SEASONAL_SALE_WINDOW_DAYS = 90
HOME_CARD_LIMIT = 12


def _steam_cdn_header(app_id: int) -> str:
    return f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/header.jpg"


def _card_from_detail(
    app_id: int,
    detail: dict | None,
    catalog: Game | None,
    latest_by_game: dict[int, list],
    sale_source: str,
) -> dict:
    if detail:
        price = detail.get("price")
        currency = detail.get("currency") or "GBP"
        status = detail.get("price_status") or "unknown"
        discount = detail.get("discount") or 0
        original = detail.get("original")
        title = detail.get("name") or (catalog.title if catalog else f"App {app_id}")
        image = detail.get("header_image") or _steam_cdn_header(app_id)
    else:
        price = None
        currency = "GBP"
        status = "unknown"
        discount = 0
        original = None
        title = catalog.title if catalog else f"App {app_id}"
        image = (catalog.cover_url if catalog and catalog.cover_url else None) or _steam_cdn_header(
            app_id
        )

    lowest_gbp = None
    lowest_label = None
    if catalog and catalog.id in latest_by_game:
        for r in latest_by_game[catalog.id]:
            if float(r.price) <= 0:
                continue
            gbp = float(to_gbp_or_zero(r.price, r.currency))
            if lowest_gbp is None or gbp < lowest_gbp:
                lowest_gbp = gbp
                lowest_label = r.store.name

    if status == "paid" and price is not None:
        steam_gbp = float(to_gbp_or_zero(price, currency))
        if lowest_gbp is None or steam_gbp < lowest_gbp:
            lowest_gbp = steam_gbp
            lowest_label = "Steam"

    launch = float(catalog.launch_price) if catalog and catalog.launch_price else None
    savings = None
    if launch and lowest_gbp and launch > 0:
        savings = int(round((1 - lowest_gbp / launch) * 100))

    return {
        "app_id": app_id,
        "title": title,
        "image": image,
        "price": price,
        "currency": currency,
        "price_status": status,
        "discount": discount,
        "original": original,
        "lowest_gbp": lowest_gbp,
        "lowest_label": lowest_label or "Steam",
        "launch": launch,
        "savings": savings,
        "sale_source": sale_source,
    }


def _seasonal_app_ids(current_specials: list[dict]) -> tuple[list[int], dict[int, str]]:
    """Rank home cards from 90-day price-drop signals, then current specials.

    Steam does not expose public unit-sales history. We therefore describe this
    honestly as a *sale signal*: recorded discounted snapshots over 90 days,
    followed by Steam's current public specials. A stable fallback keeps the
    page useful on a new installation with no stored price history.
    """
    since = timezone.now() - timezone.timedelta(days=SEASONAL_SALE_WINDOW_DAYS)
    recent = (
        Game.objects.filter(steam_app_id__isnull=False)
        .annotate(
            sale_events=Count(
                "prices",
                filter=Q(prices__recorded_at__gte=since, prices__discount_percent__gt=0),
            ),
            latest_sale=Max(
                "prices__recorded_at",
                filter=Q(prices__recorded_at__gte=since, prices__discount_percent__gt=0),
            ),
        )
        .filter(sale_events__gt=0)
        .order_by("-sale_events", "-latest_sale", "title")
        .values_list("steam_app_id", flat=True)[:HOME_CARD_LIMIT]
    )

    ordered: list[int] = []
    sources: dict[int, str] = {}

    def add(app_id, source: str) -> None:
        try:
            app_id = int(app_id)
        except (TypeError, ValueError):
            return
        if app_id > 0 and app_id not in sources and len(ordered) < HOME_CARD_LIMIT:
            ordered.append(app_id)
            sources[app_id] = source

    for app_id in recent:
        add(app_id, "90-day price-drop history")
    for special in current_specials:
        add(special.get("app_id"), "Steam special right now")
    for app_id in POPULAR_APP_IDS:
        add(app_id, "Popular fallback")
    return ordered, sources


def _build_home_payload() -> dict:
    # The public Steam feed supplements local 90-day price history.
    try:
        public_specials = (steam_featured("GB").get("specials") or [])[:8]
    except Exception:
        public_specials = []
    app_ids, sale_sources = _seasonal_app_ids(public_specials)

    catalogs = {
        g.steam_app_id: g
        for g in Game.objects.filter(steam_app_id__in=app_ids).only(
            "id",
            "steam_app_id",
            "title",
            "cover_url",
            "launch_price",
            "launch_currency",
        )
        if g.steam_app_id
    }
    catalog_ids = [g.id for g in catalogs.values()]

    # Fetch only each store's current snapshot.  Looking at the most recent
    # handful of history rows can accidentally advertise an expired sale.
    latest_by_game: dict[int, list] = defaultdict(list)
    if catalog_ids:
        newest_for_store = (
            PriceRecord.objects.filter(
                game_id=OuterRef("game_id"), store_id=OuterRef("store_id")
            )
            .order_by("-recorded_at", "-pk")
            .values("pk")[:1]
        )
        rows = (
            PriceRecord.objects.filter(
                game_id__in=catalog_ids, pk=Subquery(newest_for_store)
            )
            .select_related("store")
            .order_by("-recorded_at")
        )
        for r in rows:
            latest_by_game[r.game_id].append(r)

    details: dict[int, dict | None] = {}

    def fetch(aid: int):
        try:
            return aid, get_app_details(aid, country="GB")
        except Exception:
            return aid, None

    # Cap workers — a seasonal grid is 12 titles, so no need for 12 sockets.
    with ThreadPoolExecutor(max_workers=6) as pool:
        futs = [pool.submit(fetch, aid) for aid in app_ids]
        for fut in as_completed(futs):
            aid, det = fut.result()
            details[aid] = det

    cards = [
        _card_from_detail(
            aid, details.get(aid), catalogs.get(aid), latest_by_game, sale_sources.get(aid, "")
        )
        for aid in app_ids
    ]

    hot = sorted(
        [c for c in cards if (c.get("savings") or 0) > 0 or (c.get("discount") or 0) > 0],
        key=lambda c: (-(c.get("savings") or c.get("discount") or 0), c.get("lowest_gbp") or 999),
    )[:6]

    return {
        "popular_cards": cards,
        "hot_deals": hot,
        "public_specials": public_specials,
        "seasonal_window_days": SEASONAL_SALE_WINDOW_DAYS,
    }


def home(request):
    list(messages.get_messages(request))

    payload = cache.get(HOME_CACHE_KEY)
    if payload is None:
        try:
            payload = _build_home_payload()
        except Exception:
            payload = {"popular_cards": [], "hot_deals": [], "public_specials": []}
        cache.set(HOME_CACHE_KEY, payload, HOME_CACHE_TTL)

    return render(
        request,
        "games/home.html",
        {
            "popular_cards": payload.get("popular_cards") or [],
            "hot_deals": payload.get("hot_deals") or [],
            "public_specials": payload.get("public_specials") or [],
            "seasonal_window_days": payload.get("seasonal_window_days", SEASONAL_SALE_WINDOW_DAYS),
        },
    )
