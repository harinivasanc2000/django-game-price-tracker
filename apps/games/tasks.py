"""Low-overhead background refreshes for every supported price source.

Steam is fetched directly because it is identified by app id.  Every other
official/UK source is obtained through one cached :func:`platform_bundle`
call, so a page view and a background refresh can share the same network work.
Only the best valid offer per retailer is written through ``record_snapshot``;
that keeps the append-only history useful without storing every search result.
"""

from __future__ import annotations

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
from .executors import PAGE_EXECUTOR


# Each refresh submits exactly two secondary jobs to the shared page pool
# (platform bundle + CheapShark) while its current thread handles Steam.
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


def _watch_state(game: Game) -> tuple[list[Watch], set[tuple[int, Decimal, str]]]:
    """Load all target watches and prior alert keys once per game refresh."""
    watches = list(Watch.objects.filter(game=game, target_price__isnull=False))
    if not watches:
        return [], set()
    watch_ids = [watch.pk for watch in watches]
    existing = set(
        PriceAlert.objects.filter(watch_id__in=watch_ids).values_list(
            "watch_id", "price", "currency"
        )
    )
    return watches, existing


def _check_watch_targets(
    game: Game,
    price,
    currency: str,
    store_name: str = "",
    url: str = "",
    *,
    state: tuple[list[Watch], set[tuple[int, Decimal, str]]] | None = None,
) -> int:
    """Record PriceAlert rows for every watch whose GBP target has been met.

    Returns the number of alerts created. A watch is only alerted once per
    price point (set semantics — duplicate snapshots don't spam).
    """
    watches, existing = state if state is not None else _watch_state(game)
    hits = 0
    gbp = to_gbp_or_zero(price, currency)
    try:
        source_price = Decimal(str(price))
        verified_free = source_price.is_finite() and source_price == 0
    except (InvalidOperation, TypeError, ValueError):
        verified_free = False
    # Unknown currencies also convert to zero. Only an explicitly stored zero
    # is a real free-game event that should satisfy a £0 target.
    if gbp <= 0 and not verified_free:
        return 0
    alert_currency = settings.DEFAULT_CURRENCY
    for watch in watches:
        if gbp < 0 or gbp > watch.target_price:
            continue
        key = (watch.pk, gbp, alert_currency)
        if key in existing:
            continue
        PriceAlert.objects.create(
            watch=watch,
            price=gbp,
            currency=alert_currency,
            target_price=watch.target_price,
            store=store_name[:120],
            url=normalise_public_url(url)[:1000],
        )
        existing.add(key)
        hits += 1
    return hits


def _price_decimal(value: Any) -> Decimal | None:
    """Return a database-safe positive offer price, or ``None``."""
    try:
        price = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not price.is_finite() or price <= 0 or price > MAX_REFRESH_PRICE:
        return None
    return price


def _best_offer(rows: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
    """Choose an available row, or an explicit sold-out row as state evidence."""
    available: list[tuple[Decimal, dict[str, Any]]] = []
    unavailable: list[tuple[Decimal, dict[str, Any]]] = []
    for candidate in rows or []:
        if not isinstance(candidate, dict):
            continue
        if candidate.get("has_price") is False:
            continue
        price = _price_decimal(candidate.get("price"))
        if price is None:
            continue
        currency = str(candidate.get("currency") or "GBP").upper()[:3]
        gbp = to_gbp_or_zero(price, currency)
        if gbp <= 0:
            continue
        row = dict(candidate)
        row["price"] = price
        row["currency"] = currency
        target = unavailable if candidate.get("in_stock") is False else available
        target.append((gbp, row))
    candidates = available or unavailable
    return min(candidates, key=lambda pair: pair[0])[1] if candidates else None


def _record_offer(
    game: Game,
    spec: _SourceSpec,
    row: dict[str, Any],
    watch_state: tuple[list[Watch], set[tuple[int, Decimal, str]]],
    *,
    fallback_url: str = "",
) -> tuple[bool, bool, int]:
    """Persist one source offer and return ``(observed, created, alerts)``."""
    url = normalise_public_url(row.get("url") or fallback_url)
    condition = str(row.get("condition") or "")[:50]
    is_used = spec.is_used or bool(row.get("is_used")) or condition == "used"
    store = _store(
        spec.slug,
        spec.name,
        spec.store_type,
        spec.website,
        "Compact best-offer history; source pages remain the final authority.",
    )
    record, created = record_snapshot(
        game=game,
        store=store,
        price=row["price"],
        currency=row.get("currency") or "GBP",
        original_price=row.get("original_price") or row.get("original") or row.get("retail"),
        discount_percent=row.get("discount_percent") or row.get("discount") or row.get("savings"),
        url=url,
        is_physical=spec.is_physical,
        is_used=is_used,
        condition=condition,
        in_stock=row.get("in_stock") is not False,
        notes=str(row.get("name") or spec.name)[:255],
    )
    alerts = 0
    if record.in_stock:
        alerts = _check_watch_targets(
            game,
            record.price,
            record.currency,
            store.name,
            record.url,
            state=watch_state,
        )
    return True, created, alerts


def _cheapshark_offers(deals: Iterable[dict[str, Any]], limit: int = 6):
    """Yield at most one best safe offer per CheapShark retailer."""
    per_store: dict[str, tuple[Decimal, dict[str, Any]]] = {}
    for deal in deals or []:
        row = _best_offer([deal])
        name = str((deal or {}).get("store_name") or "").strip()
        if row is None or not name:
            continue
        gbp = to_gbp_or_zero(row["price"], row["currency"])
        key = name.casefold()
        if key not in per_store or gbp < per_store[key][0]:
            row["name"] = name
            per_store[key] = (gbp, row)
    for _gbp, row in sorted(per_store.values(), key=lambda pair: pair[0])[:limit]:
        name = str(row["name"])
        slug_part = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")[:50]
        yield _SourceSpec(
            f"cs-{slug_part}" if slug_part else "cheapshark-store",
            name[:120],
            Store.StoreType.KEYSHOP,
            "https://www.cheapshark.com",
        ), row


def refresh_one_game(game: Game, country: str = "GB") -> dict:
    """Refresh one game into compact per-store, cross-platform history."""
    country = (country or "GB").strip().upper()
    if len(country) != 2 or not country.isascii() or not country.isalpha():
        country = "GB"
    result = {
        "game": game.title,
        "steam": False,
        "psn": False,
        "xbox": False,
        "nintendo": False,
        "amazon": False,
        "uk": False,
        "third_party": False,
        "sources_observed": 0,
        "snapshots_created": 0,
        "alerts_created": 0,
        "stores": [],
        "errors": [],
    }
    watch_state = _watch_state(game)

    # Start the two broad secondary lookups, then use this worker's current
    # thread for Steam. This overlaps all network work with only two extra
    # outer threads; each client and inner bundle applies its own short timeout.
    bundle_future = PAGE_EXECUTOR.submit(platform_bundle, game.title, "")
    deals_future = PAGE_EXECUTOR.submit(deals_for_title, game.title, limit=12)
    detail = None
    if game.steam_app_id:
        try:
            detail = get_app_details(game.steam_app_id, country=country)
        except Exception as exc:  # noqa: BLE001 — one source must not abort the batch
            result["errors"].append(f"steam: {exc}")

    try:
        bundle = bundle_future.result() or {}
    except Exception as exc:  # noqa: BLE001
        bundle = {}
        result["errors"].append(f"platform bundle: {exc}")
    try:
        deals = deals_future.result() or []
    except Exception as exc:  # noqa: BLE001
        deals = []
        result["errors"].append(f"cheapshark: {exc}")

    def count_record(outcome: tuple[bool, bool, int], store_name: str) -> None:
        observed, created, alerts = outcome
        if observed:
            result["sources_observed"] += 1
            result["stores"].append(store_name)
        result["snapshots_created"] += int(created)
        result["alerts_created"] += alerts

    if detail:
        status = detail.get("price_status") or "unknown"
        steam_price = detail.get("price")
        valid_free = status == "free" and steam_price is not None
        valid_paid = status == "paid" and _price_decimal(steam_price) is not None
        if valid_free or valid_paid:
            steam_row = dict(detail)
            steam_row["price"] = Decimal("0") if valid_free else _price_decimal(steam_price)
            steam_row["currency"] = detail.get("currency") or "GBP"
            steam_spec = _SourceSpec(
                "steam", "Steam", Store.StoreType.OFFICIAL,
                "https://store.steampowered.com",
            )
            # Steam is the only source that explicitly distinguishes a real
            # free game from an unknown zero; record it without _best_offer.
            count_record(
                _record_offer(game, steam_spec, steam_row, watch_state), steam_spec.name
            )
            result["steam"] = True
        else:
            result["errors"].append("steam price unavailable")
        header = normalise_public_url(detail.get("header_image"))
        if header and not game.cover_url:
            game.cover_url = header
            game.save(update_fields=["cover_url", "updated_at"])
    elif game.steam_app_id:
        result["errors"].append("steam fetch failed")

    for key, spec in _BUNDLE_SOURCES.items():
        row = _best_offer(bundle.get(key) or [])
        if row is None:
            continue
        fallback = bundle.get(key.replace("_rows", "_search_url")) or ""
        count_record(_record_offer(game, spec, row, watch_state, fallback_url=fallback), spec.name)
        if key == "psn_rows":
            result["psn"] = True
        elif key == "xbox_rows":
            result["xbox"] = True
        elif key == "nintendo_rows":
            result["nintendo"] = True
        elif key == "amazon_rows":
            result["amazon"] = True
        else:
            result["uk"] = True

    for source in bundle.get("specialist_sources") or []:
        if not isinstance(source, dict):
            continue
        spec = _SPECIALIST_SOURCES.get(str(source.get("key") or ""))
        row = _best_offer(source.get("rows") or [])
        if spec is None or row is None:
            continue
        count_record(
            _record_offer(
                game, spec, row, watch_state,
                fallback_url=source.get("search_url") or "",
            ),
            spec.name,
        )
        result["uk"] = True

    for spec, row in _cheapshark_offers(deals):
        count_record(_record_offer(game, spec, row, watch_state), spec.name)
        result["third_party"] = True

    return result


@shared_task(name="apps.games.tasks.refresh_all_tracked_prices")
def refresh_all_tracked_prices(country: str = "GB") -> dict:
    # Console/manual entries have useful title/platform data even without a
    # Steam app id, so refresh them through the all-platform bundle as well.
    games = Game.objects.filter(is_active=True).order_by("pk")
    summary = {
        "count": games.count(),
        "ok": 0,
        "partial": 0,
        "failed": 0,
        "details": [],
    }

    # Stream rows so a large catalogue does not duplicate every Game object in
    # worker memory. One malformed retailer response must not stop later games.
    for game in games.iterator(chunk_size=100):
        try:
            r = refresh_one_game(game, country=country)
        except Exception as exc:  # noqa: BLE001 — isolate one catalogue entry
            r = {
                "game": game.title,
                "sources_observed": 0,
                "snapshots_created": 0,
                "alerts_created": 0,
                "stores": [],
                "errors": [f"refresh failed: {exc}"],
            }
        summary["details"].append(r)
        if r["sources_observed"] and not r["errors"]:
            summary["ok"] += 1
        elif r["sources_observed"]:
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
