"""Public buy guide: what is on sale and where (Steam + CheapShark)."""
from __future__ import annotations

from collections import defaultdict
from django.shortcuts import render

from .clients.public_deals import buy_recommendations
from .fx import to_gbp_or_zero
from .models import Game
from .price_queries import latest_store_snapshots
from .executors import PAGE_EXECUTOR


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
    future = PAGE_EXECUTOR.submit(buy_recommendations, country)
    try:
        public = future.result(timeout=15)
    except Exception:
        # Keep rendering from tracked snapshots; cancel work that has not yet
        # started, while an already-running bounded request may warm its cache.
        future.cancel()

    games = list(
        Game.objects.filter(is_active=True)
        .only("id", "title", "steam_app_id", "slug", "launch_price", "launch_currency")
        .order_by("title")[:40]
    )
    current_by_game = defaultdict(list)
    for record in latest_store_snapshots(game.id for game in games):
        current_by_game[record.game_id].append(record)

    tracked_tips = []
    for g in games:
        candidates = []
        for record in current_by_game.get(g.id, []):
            if not record.in_stock or float(record.price) <= 0:
                continue
            gbp = to_gbp_or_zero(record.price, record.currency)
            if gbp > 0:
                candidates.append((gbp, record))
        if not candidates:
            continue
        gbp_value, rec = min(candidates, key=lambda item: item[0])
        gbp = float(gbp_value)
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
                "url": rec.url,
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
