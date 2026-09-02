"""
Home page — cached, platform-aware UK deals and sale signals.
Tracked list stays in the side drawer (not on the main screen).
"""
from __future__ import annotations

from concurrent.futures import wait
from collections import defaultdict
import math

from django.db.models import Count, Max, Q
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET

from .cache_keys import HOME_CARDS, HOME_PLATFORM_CARDS
from .cache import cached
from .clients.platform_deals import console_deals
from .clients.public_deals import steam_featured
from .clients.scrape_utils import normalise_public_url
from .clients.steam import get_app_details
from .constants import PLATFORMS, POPULAR_APP_IDS
from .fx import to_gbp_or_zero
from .models import Game
from .price_queries import latest_store_snapshots
from .executors import PAGE_EXECUTOR, cancel_pending

HOME_CACHE_KEY = HOME_CARDS
HOME_CACHE_TTL = 180  # 3 minutes — balances freshness vs Steam rate limits
SEASONAL_SALE_WINDOW_DAYS = 90
HOME_CARD_LIMIT = 12
CONSOLE_PLATFORMS = frozenset({"ps4", "ps5", "xbox", "switch"})
HOME_PLATFORM_VALUES = frozenset(value for value, _label in PLATFORMS)
HOME_PLATFORM_LABELS = dict(PLATFORMS)
CONSOLE_BROWSE_URLS = {
    "ps4": "https://store.playstation.com/en-gb/pages/deals",
    "ps5": "https://store.playstation.com/en-gb/pages/deals",
    "xbox": "https://www.xbox.com/en-gb/promotions/sales/sales-and-specials",
    "switch": (
        "https://www.nintendo.com/en-gb/Games/Nintendo-eShop/"
        "Nintendo-eShop-Sale/Nintendo-eShop-Sale-1460557.html"
    ),
}


def normalise_home_platform(value: str | None) -> str:
    """Reduce arbitrary query input to one of the six bounded feed choices."""
    platform = str(value or "").strip().lower()
    return platform if platform in HOME_PLATFORM_VALUES else ""


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
            if not r.in_stock or float(r.price) < 0:
                continue
            gbp = float(to_gbp_or_zero(r.price, r.currency))
            # Unknown currencies resolve to zero; never advertise those as free.
            if (gbp > 0 or r.price == 0) and (lowest_gbp is None or gbp < lowest_gbp):
                lowest_gbp = gbp
                lowest_label = r.store.name

    if status in {"paid", "free"} and price is not None:
        steam_gbp = float(to_gbp_or_zero(price, currency))
        valid_steam_price = status == "free" or steam_gbp > 0
        if valid_steam_price and (lowest_gbp is None or steam_gbp < lowest_gbp):
            lowest_gbp = steam_gbp
            lowest_label = "Steam"

    launch = None
    if catalog and catalog.launch_price:
        launch_gbp = to_gbp_or_zero(
            catalog.launch_price, catalog.launch_currency or "GBP"
        )
        launch = float(launch_gbp) if launch_gbp > 0 else None
    savings = None
    if launch and lowest_gbp is not None and launch > 0:
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


def _verified_gbp(value, currency: str) -> float | None:
    """Return a finite GBP price while preserving a genuine numeric zero."""
    try:
        source = float(value)
        gbp = float(to_gbp_or_zero(value, currency or "GBP"))
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(source) or not math.isfinite(gbp) or source < 0:
        return None
    # The FX helper returns zero for unknown currencies.  Only a source value
    # that is itself zero is evidence of a free offer.
    return gbp if gbp > 0 or source == 0 else None


def _local_console_deals(platform: str) -> list[dict]:
    """Build console cards from fresh tracked rows in two bounded queries."""
    games = list(
        Game.objects.filter(is_active=True, platform=platform)
        .only(
            "id",
            "title",
            "slug",
            "platform",
            "cover_url",
            "launch_price",
            "launch_currency",
        )
        .order_by("-updated_at", "title")[:80]
    )
    if not games:
        return []

    current_by_game: dict[int, list] = defaultdict(list)
    for record in latest_store_snapshots(game.id for game in games):
        if record.in_stock:
            current_by_game[record.game_id].append(record)

    cards: list[dict] = []
    for game in games:
        candidates = []
        for record in current_by_game.get(game.id, []):
            gbp = _verified_gbp(record.price, record.currency)
            if gbp is not None:
                candidates.append((gbp, record))
        if not candidates:
            continue

        current, record = min(candidates, key=lambda pair: pair[0])
        original = None
        if record.original_price is not None:
            original = _verified_gbp(record.original_price, record.currency)
        if (original is None or original <= current) and game.launch_price is not None:
            original = _verified_gbp(game.launch_price, game.launch_currency or "GBP")
        if original is not None and original <= current:
            original = None

        try:
            discount = max(0, min(int(record.discount_percent or 0), 100))
        except (TypeError, ValueError, OverflowError):
            discount = 0
        if not discount and original and original > 0:
            discount = max(0, min(round((1 - current / original) * 100), 100))

        outbound = normalise_public_url(record.url)
        cards.append(
            {
                "title": game.title,
                "platform": platform,
                "price_gbp": round(current, 2),
                "original_gbp": round(original, 2) if original is not None else None,
                "discount": discount,
                "image": normalise_public_url(game.cover_url),
                "url": outbound or reverse("games:compare", args=[game.slug]),
                "store_name": record.store.name,
                "source_kind": "tracked",
                "is_external": bool(outbound),
            }
        )
    return cards


def _merge_console_deals(*groups: list[dict]) -> list[dict]:
    """Rank discounts consistently and retain one best card per title."""
    ranked = sorted(
        (row for group in groups for row in group),
        key=lambda row: (
            -int(row.get("discount") or 0),
            float(row.get("price_gbp")) if row.get("price_gbp") is not None else 999999,
            str(row.get("title") or "").casefold(),
        ),
    )
    seen: set[str] = set()
    unique = []
    for row in ranked:
        marker = " ".join(str(row.get("title") or "").casefold().split())
        if not marker or marker in seen:
            continue
        seen.add(marker)
        unique.append(row)
        if len(unique) >= HOME_CARD_LIMIT:
            break
    return unique


def _build_console_home_payload(platform: str) -> dict:
    """Combine fresh local prices with one cached public platform deal page."""
    platform = normalise_home_platform(platform)
    if platform not in CONSOLE_PLATFORMS:
        return {"console_deals": [], "_cache_incomplete": True}

    # Start the single public feed while the local indexed query runs.  The
    # hard page deadline prevents a blocked source from delaying navigation.
    remote_future = PAGE_EXECUTOR.submit(console_deals, platform, HOME_CARD_LIMIT * 2)
    local = _local_console_deals(platform)
    completed, _ = wait([remote_future], timeout=8)
    cancel_pending([remote_future])
    remote: list[dict] = []
    if remote_future in completed:
        try:
            remote = remote_future.result() or []
        except Exception:
            remote = []
    for row in remote:
        row.setdefault("is_external", True)

    label = HOME_PLATFORM_LABELS.get(platform, platform.upper())
    cards = _merge_console_deals(local, remote)
    return {
        "console_feed": True,
        "console_deals": cards,
        "platform_label": label,
        "feed_heading": f"{label} deals and discounts",
        "feed_intro": (
            "Fresh tracked UK offers are combined with one cached public deal feed. "
            "Open a card and confirm the final edition and price before buying."
        ),
        "browse_url": CONSOLE_BROWSE_URLS[platform],
        "_cache_incomplete": remote_future not in completed or not cards,
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
        rows = latest_store_snapshots(catalog_ids).order_by("-recorded_at")
        for r in rows:
            latest_by_game[r.game_id].append(r)

    # Featured rows already contain the title, image and live price. Reuse
    # those values instead of immediately requesting the same Steam apps again.
    details: dict[int, dict | None] = {}
    for special in public_specials:
        try:
            app_id = int(special.get("app_id"))
        except (TypeError, ValueError, OverflowError):
            continue
        price = special.get("price")
        details[app_id] = {
            "name": special.get("title") or f"App {app_id}",
            "price": price,
            "currency": special.get("currency") or "GBP",
            "price_status": (
                "free" if price == 0 else "paid" if price is not None else "unknown"
            ),
            "discount": special.get("discount") or 0,
            "original": special.get("original"),
            "header_image": special.get("image") or "",
        }

    def fetch(aid: int):
        try:
            return aid, get_app_details(aid, country="GB")
        except Exception:
            return aid, None

    # Cap workers and the *whole* batch. A context-manager would wait for every
    # slow socket on exit even after a timeout, defeating graceful degradation.
    # The shared page pool keeps this responsive without allocating a thread
    # per card or per incoming request; warm Steam-client hits are immediate.
    missing_ids = [aid for aid in app_ids if aid not in details]
    futs = [PAGE_EXECUTOR.submit(fetch, aid) for aid in missing_ids]
    completed, _ = wait(futs, timeout=9)
    cancel_pending(futs)
    for fut in completed:
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
        key=lambda c: (
            -(c.get("savings") or c.get("discount") or 0),
            c["lowest_gbp"] if c.get("lowest_gbp") is not None else 999,
        ),
    )[:6]

    return {
        "popular_cards": cards,
        "hot_deals": hot,
        "public_specials": public_specials,
        "seasonal_window_days": SEASONAL_SALE_WINDOW_DAYS,
        "_cache_incomplete": len(completed) < len(futs),
    }


def _payload_for_platform(platform: str) -> dict:
    """Return one cached payload without sharing data across platforms."""
    if platform in CONSOLE_PLATFORMS:
        return cached(
            f"{HOME_PLATFORM_CARDS}:{platform}",
            lambda: _build_console_home_payload(platform),
            HOME_CACHE_TTL,
            empty_timeout=20,
        )
    return cached(
        HOME_CACHE_KEY,
        _build_home_payload,
        HOME_CACHE_TTL,
        empty_timeout=15,
    )


def _home_context(payload: dict, platform: str) -> dict:
    """Shape both full-page and AJAX fragment contexts identically."""
    context = dict(payload or {})
    context.update(
        {
            "current_platform": platform,
            "platform_label": context.get("platform_label")
            or HOME_PLATFORM_LABELS.get(platform, "All platforms"),
            "console_feed": bool(context.get("console_feed")),
            "console_deals": context.get("console_deals") or [],
            "popular_cards": context.get("popular_cards") or [],
            "hot_deals": context.get("hot_deals") or [],
            "public_specials": context.get("public_specials") or [],
            "seasonal_window_days": context.get(
                "seasonal_window_days", SEASONAL_SALE_WINDOW_DAYS
            ),
        }
    )
    return context


def _safe_home_payload(platform: str) -> dict:
    try:
        return _payload_for_platform(platform)
    except Exception:
        if platform in CONSOLE_PLATFORMS:
            label = HOME_PLATFORM_LABELS[platform]
            return {
                "console_feed": True,
                "console_deals": [],
                "platform_label": label,
                "feed_heading": f"{label} deals and discounts",
                "feed_intro": "The live feed is temporarily unavailable.",
                "browse_url": CONSOLE_BROWSE_URLS[platform],
            }
        return {"popular_cards": [], "hot_deals": [], "public_specials": []}


@require_GET
def home_deals_fragment(request):
    """Return the selected server-rendered feed for progressive enhancement."""
    platform = normalise_home_platform(request.GET.get("platform"))
    context = _home_context(_safe_home_payload(platform), platform)
    return render(request, "games/_home_feed.html", context)


def home(request):
    platform = normalise_home_platform(request.GET.get("platform"))
    context = _home_context(_safe_home_payload(platform), platform)
    context["wide_layout"] = True

    return render(request, "games/home.html", context)
