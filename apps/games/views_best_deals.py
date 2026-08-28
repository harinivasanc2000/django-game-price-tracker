"""Best tracked deals + public multi-store highlights."""
from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, wait

from django.shortcuts import render
from django.utils import timezone

from .clients.public_deals import cheapshark_top_deals, steam_featured
from .fx import to_gbp_or_zero
from .models import Game
from .price_queries import latest_store_snapshots


def best_deals(request):
    """Show each game's cheapest *current* store snapshot, not its newest history row."""
    # Bound the current-snapshot query before evaluating it on larger histories.
    game_ids = list(
        Game.objects.filter(is_active=True).order_by("title").values_list("id", flat=True)[:80]
    )
    current_prices = latest_store_snapshots(game_ids).order_by("game__title")

    # Keep the page bounded while retaining all stores for each selected game.
    current_by_game = defaultdict(list)
    for record in current_prices:
        if len(current_by_game) < 80 or record.game_id in current_by_game:
            current_by_game[record.game_id].append(record)

    rows = []
    stale_before = timezone.now() - timezone.timedelta(days=7)
    for records in current_by_game.values():
        # Unknown currencies deliberately become zero in the FX helper, so
        # exclude them rather than presenting an untrustworthy bargain.
        priced = [
            (to_gbp_or_zero(rec.price, rec.currency), rec)
            for rec in records
            if rec.in_stock and float(rec.price) > 0
        ]
        priced = [(gbp, rec) for gbp, rec in priced if gbp > 0]
        if not priced:
            continue
        gbp, rec = min(priced, key=lambda pair: pair[0])
        g = rec.game
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
                "url": rec.url,
                "recorded_at": rec.recorded_at,
                # A price can remain useful, but users should know it has not
                # been checked recently before treating it as actionable.
                "is_stale": rec.recorded_at < stale_before,
                "vs_launch_pct": vs,
            }
        )
    rows.sort(key=lambda r: r["price_gbp"])

    public_cs, steam_specials = [], []
    pool = ThreadPoolExecutor(max_workers=2)
    try:
        f_cs = pool.submit(cheapshark_top_deals, limit=18, upper_price=50)
        f_steam = pool.submit(steam_featured, "GB")
        completed, _ = wait((f_cs, f_steam), timeout=12)
        if f_cs in completed:
            try:
                public_cs = f_cs.result() or []
            except Exception:
                pass
        if f_steam in completed:
            try:
                steam_specials = (f_steam.result().get("specials") or [])[:10]
            except Exception:
                pass
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

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
