"""Detail page — official storefronts first, then local UK scrapes + filters."""
from __future__ import annotations

from concurrent.futures import wait
import math

from django.http import JsonResponse
from django.shortcuts import redirect, render

from . import views as v
from .clients.cheapshark import deals_for_title
from .clients.digital_stores_bs4 import digital_search_links
from .clients.news import social_news_links, steam_news
from .clients.scrape_filters import parse_price_bound
from .clients.steam import get_app_details
from .constants import PLATFORMS, STORE_PLATFORMS
from .detail_helpers import empty_platform_bundle, similar_steam_titles
from .fx import to_gbp_or_zero
from .models import Game, Watch
from .platform_bundle import platform_bundle
from .executors import PAGE_EXECUTOR, cancel_pending

_OFFICIAL_FOR_PLATFORM = {
    "pc": ("Steam",),
    "ps4": ("PSN UK", "PlayStation Store (UK)"),
    "ps5": ("PSN UK", "PlayStation Store (UK)"),
    "xbox": ("Xbox", "Xbox / Microsoft Store"),
    "switch": ("Nintendo UK", "Nintendo eShop (UK)"),
}

CONDITION_CHOICES = [("", "Any condition"), ("new", "New"), ("used", "Used")]
DETAIL_POOL_TIMEOUT = 9.0
_PLATFORM_VALUES = frozenset(value for value, _label in PLATFORMS)
_CONDITION_VALUES = frozenset(value for value, _label in CONDITION_CHOICES)


def _normalise_country(raw: str | None) -> str:
    """Accept only a two-letter ASCII store country, defaulting to UK."""
    country = (raw or "GB").strip().upper()
    return country if len(country) == 2 and country.isascii() and country.isalpha() else "GB"


def _normalise_filters(request):
    """Canonicalise every detail/API filter before network or cache use."""
    platform = request.GET.get("platform", "").strip().lower()
    if platform not in _PLATFORM_VALUES:
        platform = ""
    condition = request.GET.get("condition", "").strip().lower()
    if condition not in _CONDITION_VALUES:
        condition = ""
    min_price = parse_price_bound(request.GET.get("min_price"))
    max_price = parse_price_bound(request.GET.get("max_price"))
    if min_price is not None and max_price is not None and min_price > max_price:
        min_price, max_price = max_price, min_price
    return _normalise_country(request.GET.get("cc")), platform, min_price, max_price, condition


def _decimal_text(value) -> str:
    return format(value.normalize(), "f") if value is not None else ""


def _sort_live_offers(offers: list[dict], platform: str) -> list[dict]:
    preferred = _OFFICIAL_FOR_PLATFORM.get((platform or "").lower(), ())

    def key(o: dict):
        store = (o.get("store") or "").strip()
        is_pref = 0 if store in preferred else 1
        kind_bias = 0 if (not preferred and o.get("kind") == "official") else 1
        try:
            price = float(o.get("price_gbp"))
        except (TypeError, ValueError, OverflowError):
            price = math.inf
        if not math.isfinite(price) or price < 0:
            price = math.inf
        # Zero is a valid free-game price and must not be treated as missing.
        return (is_pref, kind_bias if is_pref else 0, price)

    return sorted(offers, key=key)


def platform_deals_api(request, app_id: int):
    country, platform, min_price, max_price, condition = _normalise_filters(request)
    detail = get_app_details(app_id, country=country)
    if not detail:
        return JsonResponse({"error": "not found"}, status=404)
    try:
        data = platform_bundle(
            detail["name"],
            platform,
            min_price=min_price,
            max_price=max_price,
            condition=condition,
        )
    except Exception:
        data = empty_platform_bundle(detail["name"], platform)
    return JsonResponse(data)


def steam_detail(request, app_id: int):
    country, platform, min_price, max_price, condition = _normalise_filters(request)

    detail = get_app_details(app_id, country=country)
    if not detail:
        return redirect("games:steam_search")

    v._log_history(
        request,
        v.BrowseHistory.Action.VIEW,
        steam_app_id=app_id,
        title=detail["name"],
        detail_url=f"/steam/{app_id}/",
    )

    # One DB hit instead of two
    catalog = (
        Game.objects.filter(steam_app_id=app_id)
        .only(
            "id",
            "slug",
            "title",
            "steam_app_id",
            "platform",
            "launch_price",
            "launch_currency",
            "launch_price_source",
            "is_active",
        )
        .first()
    )
    already = catalog if catalog and catalog.is_active else None

    want_pc_deals = platform in ("", "pc")
    store_deals, news_items = [], []
    plat = empty_platform_bundle(detail["name"], platform)
    similar = []

    f_plat = PAGE_EXECUTOR.submit(
        platform_bundle,
        detail["name"],
        platform,
        min_price=min_price,
        max_price=max_price,
        condition=condition,
    )
    f_news = PAGE_EXECUTOR.submit(steam_news, app_id, 4)
    f_deals = PAGE_EXECUTOR.submit(deals_for_title, detail["name"], 8) if want_pc_deals else None
    f_sim = PAGE_EXECUTOR.submit(similar_steam_titles, detail["name"], app_id, country, 4)
    detail_futures = [future for future in (f_plat, f_news, f_deals, f_sim) if future]
    completed, _ = wait(detail_futures, timeout=DETAIL_POOL_TIMEOUT)
    cancel_pending(detail_futures)

    if f_plat in completed:
        try:
            plat = f_plat.result() or plat
        except Exception:
            pass
    if f_news in completed:
        try:
            news_items = f_news.result() or []
        except Exception:
            pass
    if f_deals and f_deals in completed:
        try:
            store_deals = f_deals.result() or []
        except Exception:
            pass
    if f_sim in completed:
        try:
            similar = f_sim.result() or []
        except Exception:
            pass

    if store_deals and (min_price is not None or max_price is not None):
        filtered = []
        for d in store_deals:
            try:
                gbp = float(to_gbp_or_zero(d["price"], d.get("currency") or "USD"))
            except Exception:
                filtered.append(d)
                continue
            if min_price is not None and gbp < float(min_price):
                continue
            if max_price is not None and gbp > float(max_price):
                continue
            filtered.append(d)
        store_deals = filtered

    digital_links = digital_search_links(detail["name"]) if want_pc_deals else []
    digital_rows: list = []

    psn_rows = plat.get("psn_rows") or []
    xbox_rows = plat.get("xbox_rows") or []
    nintendo_rows = plat.get("nintendo_rows") or []
    amazon_rows = plat.get("amazon_rows") or []
    specialist_sources = plat.get("specialist_sources") or []
    social_links = social_news_links(detail["name"], platform=platform)

    launch = float(catalog.launch_price) if catalog and catalog.launch_price else None
    launch_currency = (catalog.launch_currency if catalog else None) or "GBP"
    launch_source = (catalog.launch_price_source if catalog else "") or ""

    chart = v._build_chart_payload(
        already,
        detail,
        store_deals,
        launch,
        psn_rows,
        amazon_rows,
        plat.get("cex_rows") or [],
        plat.get("ebay_rows") or [],
        launch_currency=launch_currency,
        # Include every priced UK source returned by the platform bundle. The
        # chart helper de-duplicates a seller at the shared live timestamp.
        live_store_rows=[
            ("Xbox / Microsoft Store", xbox_rows, "GBP"),
            ("Nintendo eShop (UK)", nintendo_rows, "GBP"),
            ("GAME UK", plat.get("game_rows") or [], "GBP"),
            ("Smyths Toys", plat.get("smyths_rows") or [], "GBP"),
            ("Argos", plat.get("argos_rows") or [], "GBP"),
            ("Currys", plat.get("currys_rows") or [], "GBP"),
            ("MusicMagpie", plat.get("musicmagpie_rows") or [], "GBP"),
            *[
                (source.get("label"), source.get("rows") or [], "GBP")
                for source in specialist_sources
            ],
        ],
    )

    live_offers: list[dict] = []

    def append_offer(
        rows,
        store: str,
        kind: str,
        *,
        default_currency: str = "GBP",
        fallback_url: str = "",
        require_has_price: bool = False,
        allow_free: bool = False,
    ) -> None:
        """Append the first purchasable row with a trustworthy GBP conversion."""
        for row in rows or []:
            if not isinstance(row, dict) or row.get("in_stock") is False:
                continue
            if require_has_price and not row.get("has_price"):
                continue
            price = row.get("price")
            currency = row.get("currency") or default_currency
            price_gbp = v._gbp_point(price, currency)
            if price_gbp is None or (price_gbp <= 0 and not allow_free):
                continue
            live_offers.append(
                {
                    "store": store,
                    "price": price,
                    "price_gbp": price_gbp,
                    "currency": currency,
                    "kind": kind,
                    "url": row.get("url") or fallback_url,
                }
            )
            return

    if detail.get("price_status") in {"paid", "free"}:
        append_offer(
            [detail],
            "Steam",
            "official",
            default_currency=detail.get("currency") or "GBP",
            allow_free=detail.get("price_status") == "free",
        )
    append_offer(psn_rows, "PSN UK", "official")
    append_offer(xbox_rows, "Xbox", "official", require_has_price=True)
    append_offer(nintendo_rows, "Nintendo UK", "official", require_has_price=True)
    append_offer(amazon_rows, "Amazon UK", "marketplace")
    for key, label, kind in (
        ("game_rows", "GAME UK", "retail"),
        ("smyths_rows", "Smyths", "retail"),
        ("argos_rows", "Argos", "retail"),
        ("currys_rows", "Currys", "retail"),
        ("cex_rows", "CeX", "used"),
        ("musicmagpie_rows", "MusicMagpie", "used"),
        ("ebay_rows", "eBay UK", "marketplace"),
    ):
        append_offer(
            plat.get(key) or [],
            label,
            kind,
            fallback_url=plat.get(key.replace("_rows", "_search_url")) or "",
        )
    for source in specialist_sources:
        append_offer(
            source.get("rows") or [],
            source.get("label") or "UK specialist",
            "retail",
            fallback_url=source.get("search_url") or "",
        )
    for deal in store_deals or []:
        before = len(live_offers)
        append_offer(
            [deal],
            deal.get("store_name") or "PC retailer",
            "third-party",
            default_currency=deal.get("currency") or "USD",
        )
        if len(live_offers) > before:
            break

    live_offers = _sort_live_offers(live_offers, platform)

    watched = None
    if request.user.is_authenticated and already:
        watched = Watch.objects.filter(user=request.user, game=already).only("id", "target_price").first()

    savings_vs_launch = None
    if launch and live_offers:
        launch_gbp = float(to_gbp_or_zero(launch, launch_currency))
        offer_prices = []
        for offer in live_offers:
            try:
                offer_gbp = float(offer.get("price_gbp"))
            except (TypeError, ValueError, OverflowError):
                continue
            if math.isfinite(offer_gbp) and offer_gbp >= 0:
                offer_prices.append(offer_gbp)
        if launch_gbp > 0 and offer_prices:
            savings_vs_launch = int(round((1 - min(offer_prices) / launch_gbp) * 100))

    wallpaper = detail.get("header_image") or ""

    return render(
        request,
        "games/steam_detail.html",
        {
            "d": detail,
            "country": country,
            "platforms": PLATFORMS,
            "store_platforms": STORE_PLATFORMS,
            "condition_choices": CONDITION_CHOICES,
            "steam_os": detail.get("platforms") or [],
            "current_platform": platform,
            "min_price": _decimal_text(min_price),
            "max_price": _decimal_text(max_price),
            "condition": condition,
            "already_tracked": already,
            "catalog_game": catalog,
            "store_deals": store_deals,
            "psn_rows": psn_rows,
            "xbox_rows": xbox_rows,
            "nintendo_rows": nintendo_rows,
            "nintendo_blocked": plat.get("nintendo_blocked", True),
            "nintendo_search_url": plat.get("nintendo_search_url") or "",
            "amazon_rows": amazon_rows,
            "amazon_blocked": plat.get("amazon_blocked", True),
            "amazon_search_url": plat.get("amazon_search_url"),
            "cex_rows": plat.get("cex_rows") or [],
            "cex_blocked": plat.get("cex_blocked", True),
            "cex_search_url": plat.get("cex_search_url"),
            "ebay_rows": plat.get("ebay_rows") or [],
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
            "smyths_rows": plat.get("smyths_rows") or [],
            "smyths_blocked": plat.get("smyths_blocked", True),
            "smyths_search_url": plat.get("smyths_search_url"),
            "musicmagpie_rows": plat.get("musicmagpie_rows") or [],
            "musicmagpie_blocked": plat.get("musicmagpie_blocked", True),
            "musicmagpie_search_url": plat.get("musicmagpie_search_url"),
            "specialist_sources": specialist_sources,
            "best_local": plat.get("best_local") or [],
            "stores_ok": plat.get("stores_ok") or 0,
            "stores_total": plat.get("stores_total") or 11,
            "uk_links": plat.get("uk_links") or [],
            "digital_rows": digital_rows,
            "digital_links": digital_links,
            "news_items": news_items,
            "social_links": social_links,
            "live_offers": live_offers,
            "launch": launch,
            "launch_currency": launch_currency,
            "launch_source": launch_source,
            "savings_vs_launch": savings_vs_launch,
            "best_third_party": store_deals[0] if store_deals else None,
            # Pass structured data through Django's json_script filter in the
            # template so store names cannot break out of an inline script.
            "chart_data": chart,
            "has_chart": bool(chart.get("has_data")),
            "watched": watched,
            "is_watched": watched is not None,
            "game_wallpaper": wallpaper,
            "screenshots": (detail.get("screenshots") or [])[:4],
            "similar_games": similar,
            "wide_layout": True,
            "app_id": app_id,
        },
    )
