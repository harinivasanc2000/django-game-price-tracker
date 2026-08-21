"""Detail page — soft-fail external calls, platform-aware light loading."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

from django.http import JsonResponse
from django.shortcuts import redirect, render

from . import views as v
from .clients.cheapshark import deals_for_title
from .clients.digital_stores_bs4 import digital_search_links
from .clients.news import social_news_links, steam_news
from .clients.steam import get_app_details
from .constants import PLATFORMS, STORE_PLATFORMS
from .detail_helpers import empty_platform_bundle, similar_steam_titles
from .fx import to_gbp_or_zero
from .models import Game, Watch
from .platform_bundle import platform_bundle


def platform_deals_api(request, app_id: int):
    platform = request.GET.get("platform", "").strip().lower()
    country = request.GET.get("cc", "GB").strip().upper() or "GB"
    detail = get_app_details(app_id, country=country)
    if not detail:
        return JsonResponse({"error": "not found"}, status=404)
    try:
        data = platform_bundle(detail["name"], platform)
    except Exception:
        data = empty_platform_bundle(detail["name"], platform)
    return JsonResponse(data)


def steam_detail(request, app_id: int):
    country = request.GET.get("cc", "GB").strip().upper() or "GB"
    platform = request.GET.get("platform", "").strip().lower()
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

    # Light path: no digital BS4 scrapes on detail (links only).
    # CheapShark only for PC / All. News/similar capped.
    want_pc_deals = platform in ("", "pc")
    store_deals, news_items = [], []
    plat = empty_platform_bundle(detail["name"], platform)
    similar = []

    workers = 2 + (1 if want_pc_deals else 0)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        f_plat = pool.submit(platform_bundle, detail["name"], platform)
        f_news = pool.submit(steam_news, app_id, 5)
        f_deals = pool.submit(deals_for_title, detail["name"], 10) if want_pc_deals else None
        f_sim = pool.submit(similar_steam_titles, detail["name"], app_id, country, 4)
        try:
            plat = f_plat.result()
        except Exception:
            plat = empty_platform_bundle(detail["name"], platform)
        try:
            news_items = f_news.result() or []
        except Exception:
            news_items = []
        if f_deals:
            try:
                store_deals = f_deals.result() or []
            except Exception:
                store_deals = []
        try:
            similar = f_sim.result() or []
        except Exception:
            similar = []

    digital_links = digital_search_links(detail["name"]) if want_pc_deals else []
    digital_rows: list = []

    psn_rows = plat.get("psn_rows") or []
    xbox_rows = plat.get("xbox_rows") or []
    nintendo_rows = plat.get("nintendo_rows") or []
    amazon_rows = plat.get("amazon_rows") or []
    social_links = social_news_links(detail["name"])

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
    live_offers.sort(key=lambda x: float(x["price_gbp"]))

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
            "steam_os": detail.get("platforms") or [],
            "current_platform": platform,
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
            "has_chart": bool(chart.get("labels")),
            "watched": watched,
            "is_watched": watched is not None,
            "game_wallpaper": wallpaper,
            "screenshots": (detail.get("screenshots") or [])[:4],
            "similar_games": similar,
            "wide_layout": True,
            "app_id": app_id,
        },
    )
