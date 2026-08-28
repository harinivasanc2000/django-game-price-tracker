"""Export tracked game prices as JSON / CSV (for offline ML)."""
from __future__ import annotations

import csv
import io
from collections import defaultdict

from django.http import HttpResponse, JsonResponse
from django.utils import timezone

from .fx import to_gbp_or_zero
from .models import Game, PriceRecord
from .price_queries import latest_store_snapshots


def export_tracked_json(request):
    games = list(Game.objects.filter(is_active=True).order_by("title")[:100])
    game_ids = [game.id for game in games]
    # Export each store's current snapshot in one query. Keeping the original
    # singular ``latest`` field preserves compatibility with older consumers.
    current_by_game = defaultdict(list)
    for record in latest_store_snapshots(game_ids):
        current_by_game[record.game_id].append(record)
    payload = []
    for g in games:
        current = current_by_game.get(g.id, [])
        rec = max(current, key=lambda row: (row.recorded_at, row.pk), default=None)
        item = {
            "title": g.title,
            "slug": g.slug,
            "steam_app_id": g.steam_app_id,
            "platform": g.platform,
            "launch_price": str(g.launch_price) if g.launch_price else None,
            "launch_currency": g.launch_currency,
            "detail_url": f"/steam/{g.steam_app_id}/" if g.steam_app_id else f"/game/{g.slug}/",
        }
        if rec:
            item["latest"] = {
                "price": str(rec.price),
                "currency": rec.currency,
                "price_gbp": float(to_gbp_or_zero(rec.price, rec.currency)),
                "store": rec.store.name,
                "recorded_at": rec.recorded_at.isoformat(),
            }
        else:
            item["latest"] = None
        offers = []
        for offer in current:
            gbp = to_gbp_or_zero(offer.price, offer.currency)
            offers.append(
                {
                    "store": offer.store.name,
                    "store_type": offer.store.store_type,
                    "price": str(offer.price),
                    "currency": offer.currency,
                    "price_gbp": float(gbp) if gbp > 0 else None,
                    "in_stock": offer.in_stock,
                    "is_physical": offer.is_physical,
                    "is_used": offer.is_used,
                    "condition": offer.condition,
                    "url": offer.url,
                    "recorded_at": offer.recorded_at.isoformat(),
                }
            )
        offers.sort(
            key=lambda row: (
                not row["in_stock"],
                row["price_gbp"] is None,
                row["price_gbp"] or 0,
                row["store"].casefold(),
            )
        )
        item["current_offers"] = offers
        payload.append(item)

    return JsonResponse(
        {
            "exported_at": timezone.now().isoformat(),
            "count": len(payload),
            "games": payload,
        },
        json_dumps_params={"indent": 2},
    )


def export_training_csv(request):
    """
    Flat CSV of price snapshots for offline ML (pandas / notebooks).
    Columns are product + public price fields only — no personal data.
    """
    # Query parameters are user input: malformed or negative limits should not 500.
    try:
        limit = int(request.GET.get("limit", 5000) or 5000)
    except (TypeError, ValueError):
        limit = 5000
    limit = max(1, min(limit, 20000))
    qs = (
        PriceRecord.objects.select_related("game", "store")
        .order_by("-recorded_at")[:limit]
    )

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "recorded_at",
            "game_title",
            "game_slug",
            "steam_app_id",
            "platform",
            "launch_price",
            "launch_currency",
            "store_name",
            "store_type",
            "price",
            "currency",
            "price_gbp",
            "original_price",
            "discount_percent",
            "is_physical",
            "is_used",
            "in_stock",
            "url",
        ]
    )
    for rec in qs:
        g = rec.game
        writer.writerow(
            [
                rec.recorded_at.isoformat(),
                g.title,
                g.slug,
                g.steam_app_id or "",
                g.platform,
                str(g.launch_price) if g.launch_price is not None else "",
                g.launch_currency or "GBP",
                rec.store.name,
                rec.store.store_type,
                str(rec.price),
                rec.currency,
                f"{float(to_gbp_or_zero(rec.price, rec.currency)):.4f}",
                str(rec.original_price) if rec.original_price is not None else "",
                rec.discount_percent if rec.discount_percent is not None else "",
                int(rec.is_physical),
                int(rec.is_used),
                int(rec.in_stock),
                rec.url or "",
            ]
        )

    body = buf.getvalue()
    resp = HttpResponse(body, content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = (
        f'attachment; filename="price_training_{timezone.now():%Y%m%d_%H%M}.csv"'
    )
    return resp
