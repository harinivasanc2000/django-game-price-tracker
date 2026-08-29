"""Low-overhead background refreshes for every supported price source.

Steam is fetched directly because it is identified by app id.  Every other
official/UK source is obtained through one cached :func:`platform_bundle`
call, so a page view and a background refresh can share the same network work.
Only the best valid offer per retailer is written through ``record_snapshot``;
that keeps the append-only history useful without storing every search result.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re
from typing import Any, Iterable

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from .models import Game, Store, AdminChangeLog, Watch, PriceAlert
from .fx import to_gbp_or_zero
from .clients.scrape_utils import normalise_public_url
from .clients.steam import get_app_details
from .clients.cheapshark import deals_for_title
from .platform_bundle import platform_bundle
from .price_snapshots import record_snapshot


# Keep the refresh fan-out deliberately small. ``platform_bundle`` performs its
# own bounded source fan-out; this outer pool only overlaps that cached lookup
# with CheapShark and always waits for both workers before returning.
REFRESH_WORKERS = 2
MAX_REFRESH_PRICE = Decimal("99999999.99")


@dataclass(frozen=True, slots=True)
class _SourceSpec:
    """Stable database identity and storage defaults for a bundle source."""

    slug: str
    name: str
    store_type: str
    website: str
    is_physical: bool = False
    is_used: bool = False


# The bundle keys are part of the internal API shared by the detail page and
# refresh worker. One Store row per source gives PriceRecord a compact and
# query-friendly cross-platform series without requiring another table.
_BUNDLE_SOURCES: dict[str, _SourceSpec] = {
    "psn_rows": _SourceSpec(
        "psn-uk", "PlayStation Store (UK)", Store.StoreType.OFFICIAL,
        "https://store.playstation.com/en-gb",
    ),
    "xbox_rows": _SourceSpec(
        "xbox-uk", "Xbox / Microsoft Store", Store.StoreType.OFFICIAL,
        "https://www.xbox.com/en-GB",
    ),
    "nintendo_rows": _SourceSpec(
        "nintendo-eshop-uk", "Nintendo eShop (UK)", Store.StoreType.OFFICIAL,
        "https://www.nintendo.com/en-gb/",
    ),
    "amazon_rows": _SourceSpec(
        "amazon-uk", "Amazon UK", Store.StoreType.MARKETPLACE,
        "https://www.amazon.co.uk", is_physical=True,
    ),
    "cex_rows": _SourceSpec(
        "cex-uk", "CeX", Store.StoreType.PHYSICAL, "https://uk.webuy.com",
        is_physical=True, is_used=True,
    ),
    "ebay_rows": _SourceSpec(
        "ebay-uk", "eBay UK", Store.StoreType.MARKETPLACE,
        "https://www.ebay.co.uk", is_physical=True,
    ),
    "game_rows": _SourceSpec(
        "game-uk", "GAME UK", Store.StoreType.PHYSICAL,
        "https://www.game.co.uk", is_physical=True,
    ),
    "argos_rows": _SourceSpec(
        "argos-uk", "Argos", Store.StoreType.PHYSICAL,
        "https://www.argos.co.uk", is_physical=True,
    ),
    "currys_rows": _SourceSpec(
        "currys-uk", "Currys", Store.StoreType.PHYSICAL,
        "https://www.currys.co.uk", is_physical=True,
    ),
    "smyths_rows": _SourceSpec(
        "smyths-uk", "Smyths Toys", Store.StoreType.PHYSICAL,
        "https://www.smythstoys.com/uk/en-gb", is_physical=True,
    ),
    "musicmagpie_rows": _SourceSpec(
        "musicmagpie-uk", "MusicMagpie", Store.StoreType.PHYSICAL,
        "https://www.musicmagpie.co.uk", is_physical=True, is_used=True,
    ),
}

_SPECIALIST_SOURCES: dict[str, _SourceSpec] = {
    "the_game_collection": _SourceSpec(
        "the-game-collection", "The Game Collection", Store.StoreType.PHYSICAL,
        "https://www.thegamecollection.net", is_physical=True,
    ),
    "hit": _SourceSpec(
        "hit-uk", "Hit", Store.StoreType.PHYSICAL,
        "https://hit.co.uk", is_physical=True,
    ),
    "shopto": _SourceSpec(
        "shopto-uk", "ShopTo", Store.StoreType.PHYSICAL,
        "https://www.shopto.net", is_physical=True,
    ),
    "simplygames": _SourceSpec(
        "simplygames-uk", "SimplyGames", Store.StoreType.PHYSICAL,
        "https://www.simplygames.com", is_physical=True,
    ),
}


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


def _check_watch_targets(game: Game, price, currency: str, store_name: str = "", url: str = "") -> int:
    """Record PriceAlert rows for every watch whose GBP target has been met.

    Returns the number of alerts created. A watch is only alerted once per
    price point (set semantics — duplicate snapshots don't spam).
    """
    watches = Watch.objects.filter(game=game, target_price__isnull=False).select_related("user")
    hits = 0
    gbp = to_gbp_or_zero(price, currency)
    for watch in watches:
        if gbp <= 0 or gbp > watch.target_price:
            continue
        exists = PriceAlert.objects.filter(
            watch=watch, price=gbp, currency=settings.DEFAULT_CURRENCY
        ).exists()
        if exists:
            continue
        PriceAlert.objects.create(
            watch=watch,
            price=gbp,
            currency=settings.DEFAULT_CURRENCY,
            target_price=watch.target_price,
            store=store_name[:120],
            url=url[:1000],
        )
        hits += 1
    return hits


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
        if status != "unknown" and detail.get("price") is not None:
            # Only persist a zero price when the source explicitly reports a free game.
            price = detail["price"]
            original = detail.get("original")
            discount = detail.get("discount") or None
            notes = detail["name"][:255]
            rec, _ = record_snapshot(
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
            _check_watch_targets(game, rec.price, rec.currency, steam.name, rec.url)
            result["steam"] = True
        else:
            result["errors"].append("steam price unavailable")
        if detail.get("header_image") and not game.cover_url:
            game.cover_url = detail["header_image"]
            game.save(update_fields=["cover_url", "updated_at"])
    else:
        result["errors"].append("steam fetch failed")

    # These sources are independent network calls. Fetch them concurrently,
    # then perform all ORM writes in this main thread (important for SQLite).
    # The batch deadline keeps one slow shop from delaying every tracked game.
    secondary = {}
    pool = ThreadPoolExecutor(max_workers=3)
    futures = {
        "psn": pool.submit(best_psn_deal, game.title),
        "amazon": pool.submit(search_amazon_uk, game.title, limit=3),
        "cheapshark": pool.submit(deals_for_title, game.title, limit=5),
    }
    try:
        completed, _ = wait(tuple(futures.values()), timeout=18)
        for source, future in futures.items():
            if future not in completed:
                result["errors"].append(f"{source}: timeout")
                continue
            try:
                secondary[source] = future.result()
            except Exception as exc:  # noqa: BLE001 — each source soft-fails
                result["errors"].append(f"{source}: {exc}")
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    # PSN UK
    try:
        psn = secondary.get("psn")
        if psn and psn.get("price") is not None and float(psn["price"]) > 0:
            store = _store(
                "psn-uk",
                "PlayStation Store (UK)",
                Store.StoreType.OFFICIAL,
                "https://store.playstation.com/en-gb",
                "Public Chihiro tumbler search",
            )
            rec, _ = record_snapshot(
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
            _check_watch_targets(game, rec.price, rec.currency, store.name, rec.url)
            result["psn"] = True
    except Exception as exc:  # noqa: BLE001
        result["errors"].append(f"psn: {exc}")

    # Amazon UK (often WAF-blocked)
    try:
        amz = secondary.get("amazon") or {}
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
            rec, _ = record_snapshot(
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
            _check_watch_targets(game, rec.price, rec.currency, store.name, rec.url)
            result["amazon"] = True
    except Exception as exc:  # noqa: BLE001
        result["errors"].append(f"amazon: {exc}")

    # CheapShark
    try:
        deals = secondary.get("cheapshark") or []
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
            rec, _ = record_snapshot(
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
            _check_watch_targets(game, rec.price, rec.currency, tp.name, rec.url)
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

    # Flush any alerts that were produced during the refresh.
    try:
        send_pending_alerts.delay()
    except Exception:  # noqa: BLE001
        pass

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
    result = refresh_one_game(game, country=country)
    try:
        send_pending_alerts.delay()
    except Exception:  # noqa: BLE001
        pass
    return result


@shared_task(name="apps.games.tasks.send_pending_alerts")
def send_pending_alerts() -> dict:
    """Email every unsent PriceAlert, then mark them as sent."""
    pending = list(
        PriceAlert.objects.filter(is_sent=False)
        .select_related("watch__user", "watch__game")
        .order_by("created_at")[:100]
    )
    if not pending:
        return {"sent": 0}

    site_url = getattr(settings, "SITE_URL", "http://127.0.0.1:8000").rstrip("/")
    sent = 0
    for alert in pending:
        game = alert.watch.game
        user = alert.watch.user
        if not user.email:
            # No email address — leave unsent so admins can inspect.
            continue
        link = f"{site_url}/game/{game.slug}/"
        subject = f"Price drop: {game.title} at {alert.price} {alert.currency}"
        deal_line = f"Open deal: {alert.url}\n" if alert.url else ""
        message = (
            f"{game.title} is now {alert.price} {alert.currency} "
            f"(your target: {alert.target_price} {alert.currency}).\n"
            f"Store: {alert.store or 'n/a'}\n\n"
            f"{deal_line}"
            f"View tracker: {link}\n"
        )
        try:
            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email])
            alert.is_sent = True
            alert.sent_at = timezone.now()
            alert.save(update_fields=["is_sent", "sent_at"])
            sent += 1
        except Exception:  # noqa: BLE001 — SMTP hiccup shouldn't kill the refresh
            continue
    return {"sent": sent, "pending": len(pending)}
