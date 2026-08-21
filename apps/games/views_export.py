"""Export tracked game prices as JSON / CSV (for offline ML)."""
from __future__ import annotations

import csv
import io

from django.http import HttpResponse, JsonResponse
from django.db.models import OuterRef, Subquery
from django.utils import timezone

from .fx import to_gbp_or_zero
from .models import Game, PriceRecord


def export_tracked_json(request):
    games = list(Game.objects.filter(is_active=True).order_by("title")[:100])
    game_ids = [game.id for game in games]
    # One query for all newest rows instead of one query per exported game.
    newest_price = (
        PriceRecord.objects.filter(game_id=OuterRef("game_id"))
        .order_by("-recorded_at", "-pk")
        .values("pk")[:1]
    )
    latest_by_game = {
        record.game_id: record
        for record in PriceRecord.objects.filter(
            game_id__in=game_ids, pk=Subquery(newest_price)
        ).select_related("store")
    }
    payload = []
    for g in games:
        rec = latest_by_game.get(g.id)
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
