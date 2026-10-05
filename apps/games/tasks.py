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
from typing import Any

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from .models import Game, Store, AdminChangeLog, Watch, PriceAlert
from .fx import to_gbp_or_zero
from .clients.steam import get_app_details
from .clients.cheapshark import deals_for_title
from .platform_bundle import platform_bundle
from .price_snapshots import record_snapshot


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


_BUNDLE_SOURCES: dict[str, _SourceSpec] = {
    "psn_rows": _SourceSpec(
        "psn-uk",
        "PlayStation Store (UK)",
        Store.StoreType.OFFICIAL,
        "https://store.playstation.com/en-gb",
    ),
    "xbox_rows": _SourceSpec(
        "xbox-uk",
        "Xbox / Microsoft Store",
        Store.StoreType.OFFICIAL,
        "https://www.xbox.com/en-GB",
    ),
    "nintendo_rows": _SourceSpec(
        "nintendo-eshop-uk",
        "Nintendo eShop (UK)",
        Store.StoreType.OFFICIAL,
        "https://www.nintendo.com/en-gb/",
    ),
    "amazon_rows": _SourceSpec(
        "amazon-uk",
        "Amazon UK",
        Store.StoreType.MARKETPLACE,
        "https://www.amazon.co.uk",
        is_physical=True,
    ),
    "cex_rows": _SourceSpec(
        "cex-uk",
        "CeX",
        Store.StoreType.PHYSICAL,
        "https://uk.webuy.com",
        is_physical=True,
        is_used=True,
    ),
    "ebay_rows": _SourceSpec(
        "ebay-uk",
        "eBay UK",
        Store.StoreType.MARKETPLACE,
        "https://www.ebay.co.uk",
        is_physical=True,
    ),
    "game_rows": _SourceSpec(
        "game-uk",
        "GAME UK",
        Store.StoreType.PHYSICAL,
        "https://www.game.co.uk",
        is_physical=True,
    ),
    "argos_rows": _SourceSpec(
        "argos-uk",
        "Argos",
        Store.StoreType.PHYSICAL,
        "https://www.argos.co.uk",
        is_physical=True,
    ),
    "currys_rows": _SourceSpec(
        "currys-uk",
        "Currys",
        Store.StoreType.PHYSICAL,
        "https://www.currys.co.uk",
        is_physical=True,
    ),
    "smyths_rows": _SourceSpec(
        "smyths-uk",
        "Smyths Toys",
        Store.StoreType.PHYSICAL,
        "https://www.smythstoys.com/uk/en-gb",
        is_physical=True,
    ),
    "musicmagpie_rows": _SourceSpec(
        "musicmagpie-uk",
        "MusicMagpie",
        Store.StoreType.PHYSICAL,
        "https://www.musicmagpie.co.uk",
        is_physical=True,
        is_used=True,
    ),
}

_SPECIALIST_SOURCES: dict[str, _SourceSpec] = {
    "the_game_collection": _SourceSpec(
        "the-game-collection",
        "The Game Collection",
        Store.StoreType.PHYSICAL,
        "https://www.thegamecollection.net",
        is_physical=True,
    ),
    "hit": _SourceSpec(
        "hit-uk",
        "Hit",
        Store.StoreType.PHYSICAL,
        "https://hit.co.uk",
        is_physical=True,
    ),
    "shopto": _SourceSpec(
        "shopto-uk",
        "ShopTo",
        Store.StoreType.PHYSICAL,
        "https://www.shopto.net",
        is_physical=True,
    ),
    "simplygames": _SourceSpec(
        "simplygames-uk",
        "SimplyGames",
        Store.StoreType.PHYSICAL,
        "https://www.simplygames.com",
        is_physical=True,
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


def _as_price(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        price = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not price.is_finite() or price < 0 or price > MAX_REFRESH_PRICE:
        return None
    return price


def _best_row(rows: list[dict] | None) -> dict | None:
    """Cheapest in-stock row with a usable price."""
    best: dict | None = None
    best_price: Decimal | None = None
    for row in rows or []:
        if row.get("in_stock") is False:
            continue
        price = _as_price(row.get("price"))
        if price is None or price <= 0:
            # Free only when explicitly marked free
            if str(row.get("price_status") or "").lower() == "free":
                price = Decimal("0")
            else:
                continue
        if best_price is None or price < best_price:
            best = row
            best_price = price
    return best


def _snapshot_row(
    game: Game,
    spec: _SourceSpec,
    row: dict,
    *,
    notes: str = "",
) -> bool:
    price = _as_price(row.get("price"))
    if price is None:
        return False
    if price == 0 and str(row.get("price_status") or "").lower() != "free":
        return False

    is_used = bool(row.get("is_used")) or spec.is_used
    if str(row.get("condition") or "").lower() == "used":
        is_used = True

    currency = (row.get("currency") or "GBP").upper()[:8]
    url = (row.get("url") or "")[:1000]
    store = _store(spec.slug, spec.name, spec.store_type, spec.website)
    rec, _ = record_snapshot(
        game=game,
        store=store,
        price=price,
        currency=currency,
        original_price=_as_price(row.get("original")),
        discount_percent=row.get("discount") or row.get("savings") or None,
        url=url,
        is_physical=spec.is_physical,
        is_used=is_used,
        in_stock=row.get("in_stock") is not False,
        notes=(notes or (row.get("name") or ""))[:255],
    )
    _check_watch_targets(game, rec.price, rec.currency, store.name, rec.url)
    return True


def _check_watch_targets(
    game: Game, price, currency: str, store_name: str = "", url: str = ""
) -> int:
    """Record PriceAlert rows for every watch whose GBP target has been met."""
    watches = Watch.objects.filter(
        game=game, target_price__isnull=False
    ).select_related("user")
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
    """Refresh Steam + every platform_bundle source + best CheapShark deal."""
    result: dict[str, Any] = {
        "game": game.title,
        "steam": False,
        "bundle": False,
        "third_party": False,
        "sources": 0,
        "errors": [],
    }

    if not game.steam_app_id:
        result["errors"].append("no steam_app_id")
        return result

    detail = get_app_details(game.steam_app_id, country=country)
    if detail:
        steam = _store(
            "steam",
            "Steam",
            Store.StoreType.OFFICIAL,
            "https://store.steampowered.com",
            "Official PC digital",
        )
        status = detail.get("price_status") or "unknown"
        if status != "unknown" and detail.get("price") is not None:
            price = detail["price"]
            rec, _ = record_snapshot(
                game=game,
                store=steam,
                price=price,
                currency=detail.get("currency") or "GBP",
                original_price=detail.get("original"),
                discount_percent=detail.get("discount") or None,
                url=detail.get("url") or "",
                is_physical=False,
                is_used=False,
                in_stock=True,
                notes=(detail.get("name") or game.title)[:255],
            )
            _check_watch_targets(game, rec.price, rec.currency, steam.name, rec.url)
            result["steam"] = True
            result["sources"] += 1
        else:
            result["errors"].append("steam price unavailable")
        if detail.get("header_image") and not game.cover_url:
            game.cover_url = detail["header_image"]
            game.save(update_fields=["cover_url", "updated_at"])
        title = detail.get("name") or game.title
    else:
        result["errors"].append("steam fetch failed")
        title = game.title

    # One cached multi-store fetch + CheapShark in parallel
    secondary: dict[str, Any] = {}
    pool = ThreadPoolExecutor(max_workers=REFRESH_WORKERS)
    futures = {
        "bundle": pool.submit(platform_bundle, title, ""),
        "cheapshark": pool.submit(deals_for_title, title, 5),
    }
    try:
        completed, _ = wait(tuple(futures.values()), timeout=18)
        for source, future in futures.items():
            if future not in completed:
                result["errors"].append(f"{source}: timeout")
                continue
            try:
                secondary[source] = future.result()
            except Exception as exc:  # noqa: BLE001
                result["errors"].append(f"{source}: {exc}")
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    # Persist best row per official / UK retailer from the shared bundle
    try:
        bundle = secondary.get("bundle") or {}
        wrote_any = False
        for key, spec in _BUNDLE_SOURCES.items():
            row = _best_row(bundle.get(key))
            if not row:
                continue
            if _snapshot_row(
                game,
                spec,
                row,
                notes=f"{spec.name} {row.get('name', '')[:100]} @ {timezone.now():%Y-%m-%d}",
            ):
                wrote_any = True
                result["sources"] += 1

        for item in bundle.get("specialist_sources") or []:
            key = item.get("key") or ""
            spec = _SPECIALIST_SOURCES.get(key)
            if not spec:
                continue
            row = _best_row(item.get("rows"))
            if not row:
                continue
            if _snapshot_row(
                game,
                spec,
                row,
                notes=f"{spec.name} {row.get('name', '')[:100]} @ {timezone.now():%Y-%m-%d}",
            ):
                wrote_any = True
                result["sources"] += 1

        result["bundle"] = wrote_any
    except Exception as exc:  # noqa: BLE001
        result["errors"].append(f"bundle: {exc}")

    # CheapShark best deal (may include keyshops)
    try:
        deals = secondary.get("cheapshark") or []
        if deals:
            best = deals[0]
            slug = "cs-" + "".join(
                c if c.isalnum() else "-" for c in str(best.get("store_name") or "deal").lower()
            )[:40].strip("-")
            tp = _store(
                slug or "cheapshark-best",
                str(best.get("store_name") or "Keyshop")[:120],
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
            result["sources"] += 1
    except Exception as exc:  # noqa: BLE001
        result["errors"].append(f"cheapshark: {exc}")

    # Compatibility flags used by older summary code
    result["psn"] = bool(result.get("bundle"))
    result["amazon"] = bool(result.get("bundle"))
    return result


@shared_task(name="apps.games.tasks.refresh_all_tracked_prices")
def refresh_all_tracked_prices(country: str = "GB") -> dict:
    games = list(Game.objects.filter(is_active=True, steam_app_id__isnull=False))
    summary = {"count": len(games), "ok": 0, "partial": 0, "failed": 0, "details": []}

    for game in games:
        r = refresh_one_game(game, country=country)
        summary["details"].append(r)
        if r.get("steam") and r.get("bundle"):
            summary["ok"] += 1
        elif r.get("sources", 0) > 0:
            summary["partial"] += 1
        else:
            summary["failed"] += 1

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
        except Exception:  # noqa: BLE001
            continue
    return {"sent": sent, "pending": len(pending)}
