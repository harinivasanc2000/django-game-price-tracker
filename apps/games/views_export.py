"""Export tracked game prices as JSON / CSV (for offline ML)."""
from __future__ import annotations

import csv
import io

from django.http import HttpResponse, JsonResponse
from django.utils import timezone

from .fx import to_gbp_or_zero
from .models import Game, PriceRecord


def export_tracked_json(request):
    games = list(Game.objects.filter(is_active=True).order_by("title")[:100])
    payload = []
    for g in games:
        rec = (
            PriceRecord.objects.filter(game=g)
            .select_related("store")
            .order_by("-recorded_at")
            .first()
        )
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
    limit = min(int(request.GET.get("limit", 5000) or 5000), 20000)
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
