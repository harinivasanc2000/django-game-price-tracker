"""
Background price refresh tasks.

- Steam (official, region-aware)
- PSN UK (public tumbler search)
- CheapShark best deal (third-party / key shops)
- Amazon UK when HTML is available (often blocked by WAF)
"""

from __future__ import annotations

from decimal import Decimal
from celery import shared_task
from django.utils import timezone

from .models import Game, PriceRecord, Store, AdminChangeLog
from .clients.steam import get_app_details
from .clients.cheapshark import deals_for_title
from .clients.psn import best_psn_deal
from .clients.amazon_uk import search_amazon_uk


def _store(slug: str, name: str, store_type: str, website: str = "", notes: str = "") -> Store:
    obj, _ = Store.objects.get_or_create(
        slug=slug,
        defaults={
            "name": name,
            "website": website,
            "store_type": store_type,
            "country": "GB",
            "notes": notes,
        },
    )
    return obj


def refresh_one_game(game: Game, country: str = "GB") -> dict:
    result = {
        "game": game.title,
        "steam": False,
        "psn": False,
        "amazon": False,
        "third_party": False,
        "errors": [],
    }

    if not game.steam_app_id:
        result["errors"].append("no steam_app_id")
        return result

    detail = get_app_details(game.steam_app_id, country=country)
    if detail:
        steam = _store(
            "steam", "Steam", Store.StoreType.OFFICIAL,
            "https://store.steampowered.com", "Official PC digital",
        )
        status = detail.get("price_status") or "unknown"
        if status == "unknown" or detail.get("price") is None:
            price = Decimal("0.00")
            original = None
            discount = None
            notes = f"{detail['name'][:180]} [unknown] @ {timezone.now():%Y-%m-%d}"
        else:
            price = detail["price"] or Decimal("0.00")
            original = detail.get("original")
            discount = detail.get("discount") or None
            notes = detail["name"][:255]

        PriceRecord.objects.create(
            game=game,
            store=steam,
            price=price,
            currency=detail.get("currency") or "GBP",
            original_price=original,
            discount_percent=discount,
            url=detail.get("url") or "",
            is_physical=False,
            is_used=False,
            in_stock=True,
            notes=notes,
        )
        if detail.get("header_image") and not game.cover_url:
            game.cover_url = detail["header_image"]
            game.save(update_fields=["cover_url", "updated_at"])
        result["steam"] = True
    else:
        result["errors"].append("steam fetch failed")

    # PSN UK
    try:
        psn = best_psn_deal(game.title)
        if psn and psn.get("price") is not None and float(psn["price"]) > 0:
            store = _store(
                "psn-uk",
                "PlayStation Store (UK)",
                Store.StoreType.OFFICIAL,
                "https://store.playstation.com/en-gb",
                "Public Chihiro tumbler search",
            )
            PriceRecord.objects.create(
                game=game,
                store=store,
                price=psn["price"],
                currency="GBP",
                original_price=None,
                discount_percent=None,
                url=psn.get("url") or "",
                is_physical=False,
                is_used=False,
                in_stock=True,
                notes=f"PSN {psn.get('name','')[:120]} @ {timezone.now():%Y-%m-%d}",
            )
            result["psn"] = True
    except Exception as exc:  # noqa: BLE001
        result["errors"].append(f"psn: {exc}")

    # Amazon UK (often WAF-blocked)
    try:
        amz = search_amazon_uk(game.title, limit=3)
        rows = amz.get("results") or []
        if rows:
            store = _store(
                "amazon-uk",
                "Amazon UK",
                Store.StoreType.MARKETPLACE,
                "https://www.amazon.co.uk",
                "Public search HTML when available",
            )
            row = rows[0]
            PriceRecord.objects.create(
                game=game,
                store=store,
                price=row["price"],
                currency="GBP",
                url=row.get("url") or "",
                is_physical=True,
                is_used=False,
                in_stock=True,
                notes=f"Amazon {row.get('name','')[:100]} @ {timezone.now():%Y-%m-%d}",
            )
            result["amazon"] = True
    except Exception as exc:  # noqa: BLE001
        result["errors"].append(f"amazon: {exc}")

    # CheapShark
    try:
        deals = deals_for_title(game.title, limit=5)
        if deals:
            best = deals[0]
            slug = "cs-" + "".join(
                c if c.isalnum() else "-" for c in best["store_name"].lower()
            )[:40].strip("-")
            tp = _store(
                slug or "cheapshark-best",
                best["store_name"][:120],
                Store.StoreType.KEYSHOP,
                best.get("url") or "https://www.cheapshark.com",
                "Via CheapShark — may include keyshops. Verify seller.",
            )
            PriceRecord.objects.create(
                game=game,
                store=tp,
                price=best["price"],
                currency=best.get("currency") or "USD",
                original_price=best.get("retail") or None,
                discount_percent=best.get("savings") or None,
                url=best.get("url") or "",
                is_physical=False,
                is_used=False,
                in_stock=True,
                notes=f"CheapShark best @ {timezone.now():%Y-%m-%d} [third-party]",
            )
            result["third_party"] = True
    except Exception as exc:  # noqa: BLE001
        result["errors"].append(f"cheapshark: {exc}")

    return result


@shared_task(name="apps.games.tasks.refresh_all_tracked_prices")
def refresh_all_tracked_prices(country: str = "GB") -> dict:
    games = list(Game.objects.filter(is_active=True, steam_app_id__isnull=False))
    summary = {"count": len(games), "ok": 0, "partial": 0, "failed": 0, "details": []}

    for game in games:
        r = refresh_one_game(game, country=country)
        summary["details"].append(r)
        flags = [r["steam"], r["psn"], r["amazon"], r["third_party"]]
        if all(flags[:2]):  # steam+psn at least
            summary["ok"] += 1
        elif any(flags):
            summary["partial"] += 1
        else:
            summary["failed"] += 1

    AdminChangeLog.objects.create(
        actor="celery",
        action="refresh_all_tracked_prices",
        details=(
            f"games={summary['count']} ok={summary['ok']} "
            f"partial={summary['partial']} failed={summary['failed']} "
            f"at {timezone.now().isoformat()}"
        ),
    )
    return summary


@shared_task(name="apps.games.tasks.refresh_single_game")
def refresh_single_game(game_id: int, country: str = "GB") -> dict:
    try:
        game = Game.objects.get(pk=game_id, is_active=True)
    except Game.DoesNotExist:
        return {"error": "not found"}
    return refresh_one_game(game, country=country)
