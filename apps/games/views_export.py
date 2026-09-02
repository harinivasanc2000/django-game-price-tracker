"""Export tracked game prices as JSON / CSV (for offline ML)."""
from __future__ import annotations

import csv
import io
from collections import defaultdict

from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .fx import to_gbp_or_zero
from .models import Game, PriceRecord
from .price_queries import latest_store_snapshots


class _CsvEcho:
    """Let ``csv.writer`` yield each row directly to StreamingHttpResponse."""

    def write(self, value):
        return value


def _safe_csv_text(value) -> str:
    """Stop exported catalogue text being interpreted as a spreadsheet formula."""
    text = str(value or "")
    return f"'{text}" if text.lstrip().startswith(("=", "+", "-", "@")) else text


def _bounded_limit(raw, *, default: int, maximum: int) -> int:
    try:
        value = int(raw or default)
    except (TypeError, ValueError):
        value = default
    return max(1, min(value, maximum))


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
        rec = max(current, key=lambda row: (row.last_checked_at, row.pk), default=None)
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
                "last_checked_at": rec.last_checked_at.isoformat(),
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
                    "price_gbp": float(gbp) if gbp > 0 or offer.price == 0 else None,
                    "in_stock": offer.in_stock,
                    "is_physical": offer.is_physical,
                    "is_used": offer.is_used,
                    "condition": offer.condition,
                    "url": offer.url,
                    "recorded_at": offer.recorded_at.isoformat(),
                    "last_checked_at": offer.last_checked_at.isoformat(),
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
            "last_checked_at",
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
                rec.last_checked_at.isoformat(),
            ]
        )

    body = buf.getvalue()
    resp = HttpResponse(body, content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = (
        f'attachment; filename="price_training_{timezone.now():%Y%m%d_%H%M}.csv"'
    )
    return resp


def export_game_prices_csv(request, slug: str):
    """Stream one active game's bounded history without buffering it in RAM."""
    game = get_object_or_404(Game, slug=slug, is_active=True)
    limit = _bounded_limit(request.GET.get("limit"), default=1000, maximum=5000)
    records = (
        PriceRecord.objects.filter(game=game)
        .select_related("store")
        .order_by("-recorded_at", "-pk")[:limit]
    )

    def rows():
        writer = csv.writer(_CsvEcho())
        yield writer.writerow(
            [
                "recorded_at",
                "game_title",
                "platform",
                "store_name",
                "store_type",
                "price",
                "currency",
                "price_gbp",
                "original_price",
                "discount_percent",
                "condition",
                "is_physical",
                "is_used",
                "in_stock",
                "url",
                "last_checked_at",
            ]
        )
        # ``iterator`` keeps even the maximum 5,000-row export at constant
        # Python memory while select_related prevents a query per store.
        for record in records.iterator(chunk_size=250):
            gbp = to_gbp_or_zero(record.price, record.currency)
            yield writer.writerow(
                [
                    record.recorded_at.isoformat(),
                    _safe_csv_text(game.title),
                    _safe_csv_text(game.platform),
                    _safe_csv_text(record.store.name),
                    _safe_csv_text(record.store.store_type),
                    str(record.price),
                    _safe_csv_text(record.currency),
                    f"{float(gbp):.4f}" if gbp > 0 or record.price == 0 else "",
                    str(record.original_price) if record.original_price is not None else "",
                    record.discount_percent if record.discount_percent is not None else "",
                    _safe_csv_text(record.condition),
                    int(record.is_physical),
                    int(record.is_used),
                    int(record.in_stock),
                    _safe_csv_text(record.url),
                    record.last_checked_at.isoformat(),
                ]
            )

    response = StreamingHttpResponse(rows(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{game.slug}-price-history.csv"'
    return response
