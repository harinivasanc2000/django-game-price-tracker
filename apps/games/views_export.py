"""Export tracked game prices as JSON."""
from __future__ import annotations

from django.http import JsonResponse
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
