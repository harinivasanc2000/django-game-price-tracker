"""Detail page entrypoints with soft-fail on external scrapes."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

from django.http import JsonResponse
from django.shortcuts import redirect, render

from .clients.cheapshark import deals_for_title
from .clients.digital_stores_bs4 import digital_search_links, fetch_digital_bundle
from .clients.external_stores import ensure_uk_stores
from .clients.news import steam_news, social_news_links
from .clients.steam import get_app_details
from .detail_helpers import empty_platform_bundle, similar_steam_titles
from .fx import to_gbp_or_zero
from .models import Game, Watch
from . import views as v


def _flatten_digital(bundle: dict) -> list[dict]:
    rows = []
    for key in ("humble", "fanatical", "gmg", "gog", "cdkeys"):
        block = bundle.get(key) or {}
        for r in block.get("results") or []:
            out = {}
            for k, val in r.items():
                out[k] = float(val) if isinstance(val, Decimal) else val
            rows.append(out)
    rows.sort(key=lambda x: float(x.get("price") or 9999))
    return rows[:12]


def platform_deals_api(request, app_id: int):
    platform = request.GET.get("platform", "").strip().lower()
    country = request.GET.get("cc", "GB").strip().upper() or "GB"
    detail = get_app_details(app_id, country=country)
    if not detail:
        return JsonResponse({"error": "not found"}, status=404)
    try:
        data = v._platform_bundle(detail["name"], platform)
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

    try:
        ensure_uk_stores()
    except Exception:
        pass

    already = Game.objects.filter(steam_app_id=app_id, is_active=True).first()
    catalog = Game.objects.filter(steam_app_id=app_id).first()

    store_deals, news_items, plat = [], [], empty_platform_bundle(detail["name"], platform)
    similar = []
    digital_bundle: dict = {"digital_links": digital_search_links(detail["name"])}
    with ThreadPoolExecutor(max_workers=7) as pool:
        f_deals = pool.submit(deals_for_title, detail["name"], 15)
        f_news = pool.submit(steam_news, app_id, 8)
        f_plat = pool.submit(v._platform_bundle, detail["name"], platform)
        f_sim = pool.submit(similar_steam_titles, detail["name"], app_id, country, 6)
        f_dig = pool.submit(fetch_digital_bundle, detail["name"], 4)
        try:
            store_deals = f_deals.result() or []
        except Exception:
            store_deals = []
        try:
            news_items = f_news.result() or []
        except Exception:
            news_items = []
        try:
            plat = f_plat.result()
        except Exception:
            plat = empty_platform_bundle(detail["name"], platform)
        try:
            similar = f_sim.result() or []
        except Exception:
            similar = []
        try:
            digital_bundle = f_dig.result() or digital_bundle
        except Exception:
            pass

    digital_rows = _flatten_digital(digital_bundle)
    digital_links = digital_bundle.get("digital_links") or digital_search_links(detail["name"])

    psn_rows = plat.get("psn_rows") or []
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
    for row in digital_rows[:3]:
        live_offers.append(
            {
                "store": row.get("store_name") or "Digital",
                "price": row["price"],
                "price_gbp": to_gbp_or_zero(row["price"], row.get("currency") or "GBP"),
                "currency": row.get("currency") or "GBP",
                "kind": "third-party" if row.get("store_name") == "CDKeys" else "retail",
                "url": row.get("url"),
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

    wallpaper = (
        detail.get("library_hero")
        or detail.get("page_background")
        or detail.get("header_image")
        or ""
    )

    return render(
        request,
        "games/steam_detail.html",
        {
            "d": detail,
            "country": country,
            "platforms": v.PLATFORMS,
            "store_platforms": [
                ("pc", "PC"),
                ("ps4", "PS4"),
                ("ps5", "PS5"),
                ("xbox", "Xbox"),
                ("switch", "Switch"),
            ],
            "steam_os": detail.get("platforms") or [],
            "current_platform": platform,
            "already_tracked": already,
            "catalog_game": catalog,
            "store_deals": store_deals,
            "psn_rows": psn_rows,
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
            "screenshots": detail.get("screenshots") or [],
            "similar_games": similar,
            "wide_layout": True,
            "app_id": app_id,
        },
    )
