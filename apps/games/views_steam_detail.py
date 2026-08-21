"""Detail page — official storefronts first, then local UK scrapes + filters."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, wait
from decimal import Decimal

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

_OFFICIAL_FOR_PLATFORM = {
    "pc": ("Steam",),
    "ps4": ("PSN UK", "PlayStation Store (UK)"),
    "ps5": ("PSN UK", "PlayStation Store (UK)"),
    "xbox": ("Xbox", "Xbox / Microsoft Store"),
    "switch": ("Nintendo UK", "Nintendo eShop (UK)"),
}

CONDITION_CHOICES = [("", "Any condition"), ("new", "New"), ("used", "Used")]


def _sort_live_offers(offers: list[dict], platform: str) -> list[dict]:
    preferred = _OFFICIAL_FOR_PLATFORM.get((platform or "").lower(), ())

    def key(o: dict):
        store = (o.get("store") or "").strip()
        is_pref = 0 if store in preferred else 1
        kind_bias = 0 if (not preferred and o.get("kind") == "official") else 1
        return (is_pref, kind_bias if is_pref else 0, float(o.get("price_gbp") or 9999))

    return sorted(offers, key=key)


def platform_deals_api(request, app_id: int):
    platform = request.GET.get("platform", "").strip().lower()
    country = request.GET.get("cc", "GB").strip().upper() or "GB"
    min_price = parse_price_bound(request.GET.get("min_price"))
    max_price = parse_price_bound(request.GET.get("max_price"))
    condition = request.GET.get("condition", "").strip().lower()
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
    country = request.GET.get("cc", "GB").strip().upper() or "GB"
    platform = request.GET.get("platform", "").strip().lower()
    min_price = parse_price_bound(request.GET.get("min_price"))
    max_price = parse_price_bound(request.GET.get("max_price"))
    condition = request.GET.get("condition", "").strip().lower()

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

    already = Game.objects.filter(steam_app_id=app_id, is_active=True).only(
        "id", "slug", "title", "steam_app_id", "platform", "launch_price", "launch_currency"
    ).first()
    catalog = Game.objects.filter(steam_app_id=app_id).only(
        "id", "launch_price", "launch_currency", "launch_price_source"
    ).first()

    want_pc_deals = platform in ("", "pc")
    store_deals, news_items = [], []
    plat = empty_platform_bundle(detail["name"], platform)
    similar = []

    workers = 3 + (1 if want_pc_deals else 0)
    pool = ThreadPoolExecutor(max_workers=workers)
    try:
        f_plat = pool.submit(
            platform_bundle,
            detail["name"],
            platform,
            min_price=min_price,
            max_price=max_price,
            condition=condition,
        )
        f_news = pool.submit(steam_news, app_id, 5)
        f_deals = pool.submit(deals_for_title, detail["name"], 10) if want_pc_deals else None
        f_sim = pool.submit(similar_steam_titles, detail["name"], app_id, country, 4)
        completed, _ = wait(
            [future for future in (f_plat, f_news, f_deals, f_sim) if future], timeout=12
        )

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
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    # Apply max/min to third-party CheapShark rows when set
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
    )

    live_offers: list[dict] = []

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
    for row in xbox_rows:
        if row.get("has_price") and float(row.get("price") or 0) > 0:
            live_offers.append(
                {
                    "store": "Xbox",
                    "price": row["price"],
                    "price_gbp": to_gbp_or_zero(row["price"], row.get("currency") or "GBP"),
                    "currency": row.get("currency") or "GBP",
                    "kind": "official",
                    "url": row.get("url"),
                }
            )
            break
    for row in nintendo_rows:
        if row.get("has_price") and float(row.get("price") or 0) > 0:
            live_offers.append(
                {
                    "store": "Nintendo UK",
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
        ("game_rows", "GAME UK", "retail"),
        ("smyths_rows", "Smyths", "retail"),
        ("argos_rows", "Argos", "retail"),
        ("currys_rows", "Currys", "retail"),
        ("cex_rows", "CeX", "used"),
        ("ebay_rows", "eBay UK", "marketplace"),
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

    live_offers = _sort_live_offers(live_offers, platform)

    watched = None
    if request.user.is_authenticated and already:
        watched = Watch.objects.filter(user=request.user, game=already).first()

    savings_vs_launch = None
    if launch and live_offers:
        best_gbp = float(live_offers[0]["price_gbp"])
        if launch > 0:
            savings_vs_launch = int(round((1 - best_gbp / launch) * 100))

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
            "min_price": request.GET.get("min_price", ""),
            "max_price": request.GET.get("max_price", ""),
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
            "chart_json": json.dumps(chart),
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
