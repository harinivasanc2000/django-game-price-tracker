"""Best tracked deals + public multi-store highlights."""
from __future__ import annotations

from django.shortcuts import render

from .clients.public_deals import cheapshark_top_deals, steam_featured
from .fx import to_gbp_or_zero
from .models import Game, PriceRecord


def best_deals(request):
    games = list(Game.objects.filter(is_active=True).order_by("title")[:80])
    rows = []
    for g in games:
        rec = (
            PriceRecord.objects.filter(game=g)
            .select_related("store")
            .order_by("-recorded_at")
            .first()
        )
        if not rec or float(rec.price) <= 0:
            continue
        gbp = to_gbp_or_zero(rec.price, rec.currency)
        vs = None
        if g.launch_price and float(g.launch_price) > 0:
            launch_gbp = to_gbp_or_zero(g.launch_price, g.launch_currency or "GBP")
            if launch_gbp > 0:
                vs = int(round((1 - float(gbp) / float(launch_gbp)) * 100))
        rows.append(
            {
                "game": g,
                "price": rec.price,
                "currency": rec.currency,
                "price_gbp": gbp,
                "store": rec.store.name,
                "recorded_at": rec.recorded_at,
                "vs_launch_pct": vs,
            }
        )
    rows.sort(key=lambda r: r["price_gbp"])

    public_cs = []
    steam_specials = []
    try:
        public_cs = cheapshark_top_deals(limit=18, upper_price=50)
    except Exception:
        public_cs = []
    try:
        steam_specials = (steam_featured("GB").get("specials") or [])[:10]
    except Exception:
        steam_specials = []

    return render(
        request,
        "games/best_deals.html",
        {
            "rows": rows,
            "public_cs": public_cs,
            "steam_specials": steam_specials,
            "wide_layout": True,
        },
    )
