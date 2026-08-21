"""Public buy guide: what is on sale and where (Steam + CheapShark)."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from django.shortcuts import render

from .clients.public_deals import buy_recommendations, steam_featured
from .fx import to_gbp_or_zero
from .models import Game, PriceRecord


def buy_guide(request):
    country = (request.GET.get("cc") or "GB").strip().upper() or "GB"

    public = {
        "steam_specials": [],
        "steam_top": [],
        "steam_new": [],
        "multi_store": [],
        "smart_picks": [],
        "free_picks": [],
        "country": country,
    }
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            public = pool.submit(buy_recommendations, country).result(timeout=18)
    except Exception:
        try:
            public["steam_specials"] = (steam_featured(country).get("specials") or [])[:10]
        except Exception:
            pass

    tracked_tips = []
    for g in Game.objects.filter(is_active=True).order_by("title")[:40]:
        rec = (
            PriceRecord.objects.filter(game=g)
            .select_related("store")
            .order_by("-recorded_at")
            .first()
        )
        if not rec or float(rec.price) <= 0:
            continue
        gbp = float(to_gbp_or_zero(rec.price, rec.currency))
        vs = None
        if g.launch_price and float(g.launch_price) > 0:
            launch = float(to_gbp_or_zero(g.launch_price, g.launch_currency or "GBP"))
            if launch > 0:
                vs = int(round((1 - gbp / launch) * 100))
        tracked_tips.append(
            {
                "title": g.title,
                "app_id": g.steam_app_id,
                "slug": g.slug,
                "store": rec.store.name,
                "price_gbp": gbp,
                "vs_launch": vs,
                "kind": rec.store.store_type,
            }
        )
    tracked_tips.sort(key=lambda x: (-(x.get("vs_launch") or 0), x["price_gbp"]))

    return render(
        request,
        "games/buy_guide.html",
        {
            "wide_layout": True,
            "country": country,
            "steam_specials": public.get("steam_specials") or [],
            "steam_top": public.get("steam_top") or [],
            "steam_new": public.get("steam_new") or [],
            "multi_store": public.get("multi_store") or [],
            "smart_picks": public.get("smart_picks") or [],
            "free_picks": public.get("free_picks") or [],
            "tracked_tips": tracked_tips[:15],
        },
    )
