"""
Home page — clean deal-site style.
No tracked / recently viewed on the main screen (use drawer + History).
Popular grid with Steam header art + live UK prices.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal

from django.contrib import messages
from django.shortcuts import render

from .clients.steam import get_app_details
from .fx import to_gbp_or_zero
from .models import Game, PriceRecord

# Curated popular titles (Steam app IDs) — order = display order
POPULAR_APP_IDS = [
    1091500,  # Cyberpunk 2077
    1245620,  # ELDEN RING
    271590,   # GTA V
    1174180,  # RDR2
    1593500,  # God of War
    1086940,  # Baldur's Gate 3
    292030,   # Witcher 3
    1817070,  # Spider-Man Remastered
    814380,   # Sekiro
    1888930,  # The Last of Us Part I
    2050650,  # Resident Evil 4
    1145360,  # Hades
]


def _steam_cdn_header(app_id: int) -> str:
    return f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/header.jpg"


def _card_from_detail(app_id: int, detail: dict | None, catalog: Game | None) -> dict:
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

    # Prefer stored PriceRecord if cheaper / more recent multi-store
    lowest_gbp = None
    lowest_label = None
    if catalog:
        rec = (
            PriceRecord.objects.filter(game=catalog)
            .select_related("store")
            .order_by("-recorded_at")[:8]
        )
        for r in rec:
            if float(r.price) <= 0:
                continue
            gbp = float(to_gbp_or_zero(r.price, r.currency))
            if lowest_gbp is None or gbp < lowest_gbp:
                lowest_gbp = gbp
                lowest_label = r.store.name

    steam_gbp = None
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
    }


def home(request):
    list(messages.get_messages(request))

    catalogs = {
        g.steam_app_id: g
        for g in Game.objects.filter(steam_app_id__in=POPULAR_APP_IDS)
        if g.steam_app_id
    }

    details: dict[int, dict | None] = {}

    def fetch(aid: int):
        try:
            return aid, get_app_details(aid, country="GB")
        except Exception:
            return aid, None

    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = [pool.submit(fetch, aid) for aid in POPULAR_APP_IDS]
        for fut in as_completed(futs):
            aid, det = fut.result()
            details[aid] = det

    cards = [
        _card_from_detail(aid, details.get(aid), catalogs.get(aid))
        for aid in POPULAR_APP_IDS
    ]

    # Hot deals = biggest positive savings vs launch, then discount
    hot = sorted(
        [c for c in cards if (c.get("savings") or 0) > 0 or (c.get("discount") or 0) > 0],
        key=lambda c: (-(c.get("savings") or c.get("discount") or 0), c.get("lowest_gbp") or 999),
    )[:6]

    return render(
        request,
        "games/home.html",
        {
            "popular_cards": cards,
            "hot_deals": hot,
        },
    )
