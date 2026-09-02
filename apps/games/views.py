"""
Core views: tracking, profile, history, autocomplete, chart helpers.

Home / search / detail live in dedicated modules (home_view, search_view,
views_steam_detail) — keep this file focused on shared actions.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from .cache import bust
from .cache_keys import HOME_CARDS, TRACKED_DRAWER
from .clients.external_stores import ensure_uk_stores
from .clients.steam import get_app_details, suggest_store
from .fx import to_gbp, to_gbp_or_zero
from .models import (
    BrowseHistory,
    Game,
    PriceAlert,
    PriceRecord,
    Store,
    Watch,
)
from .price_queries import latest_store_snapshots, quote_needs_refresh
from .price_insights import build_price_insights
from .views_best_deals import best_deals  # noqa: F401
from .price_snapshots import record_snapshot

HISTORY_MAX_PER_SESSION = 100
HISTORY_PRUNE_INTERVAL = timezone.timedelta(hours=24)
HISTORY_PRUNE_MARK = timezone.timedelta(days=60)
CHART_HISTORY_LIMIT = 300
CHART_QUOTE_MAX_AGE = timezone.timedelta(days=7)


def _session_key(request):
    if not request.session.session_key:
        request.session.create()
    return request.session.session_key


def _log_history(request, action, query="", steam_app_id=None, title="", detail_url=""):
    skey = _session_key(request)
    BrowseHistory.objects.create(
        session_key=skey,
        action=action,
        query=query[:255],
        steam_app_id=steam_app_id,
        title=(title or "")[:255],
        detail_url=(detail_url or "")[:255],
    )
    # Keep only newest N per session (slice after max uses offset)
    old_ids = list(
        BrowseHistory.objects.filter(session_key=skey)
        .order_by("-created_at")
        .values_list("id", flat=True)[HISTORY_MAX_PER_SESSION:]
    )
    if old_ids:
        BrowseHistory.objects.filter(id__in=old_ids).delete()

    recently_pruned = request.session.get("history_pruned_at")
    need_prune = True
    if recently_pruned:
        try:
            # Handle both aware ISO strings and naive fallbacks
            pruned_at = datetime.fromisoformat(recently_pruned)
            if timezone.is_naive(pruned_at):
                pruned_at = timezone.make_aware(pruned_at, timezone.get_current_timezone())
            need_prune = (timezone.now() - pruned_at) > HISTORY_PRUNE_INTERVAL
        except Exception:
            need_prune = True
    if need_prune:
        BrowseHistory.objects.filter(created_at__lt=timezone.now() - HISTORY_PRUNE_MARK).delete()
        request.session["history_pruned_at"] = timezone.now().isoformat()


def _bust_ui_caches():
    bust(TRACKED_DRAWER)
    bust(HOME_CARDS)


def _unique_slug(name: str, app_id: int) -> str:
    base = slugify(f"{name}-pc")[:160] or f"steam-{app_id}"
    slug, n = base, 1
    while Game.objects.filter(slug=slug).exclude(steam_app_id=app_id).exists():
        slug = f"{base}-{app_id}" if n == 1 else f"{base}-{n}"
        n += 1
        if n > 50:
            slug = f"steam-{app_id}"
            break
    return slug[:180]


def _gbp_point(amount, currency="GBP") -> float | None:
    """Return a finite, non-negative GBP value suitable for JSON/charting."""
    try:
        v = to_gbp(amount, currency)
    except (ArithmeticError, TypeError, ValueError):
        return None
    if v is None:
        return None
    try:
        point = float(v)
    except (TypeError, ValueError, OverflowError):
        return None
    return point if math.isfinite(point) and point >= 0 else None


def _collapse_changes(pairs: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """Keep price changes, run ends, and periodic freshness confirmations.

    Refresh jobs can write the same quote many times. Keeping only the first
    quote makes it look stale, while keeping every duplicate produces a noisy
    chart. This run-length compaction preserves both ends plus checkpoints no
    more than half the quote lifetime apart.  The checkpoints matter: removing
    ten daily equal-price checks would otherwise manufacture a false seven-day
    stale gap between the first and last observation.
    """
    if not pairs:
        return []
    if len(pairs) <= 2:
        return pairs

    out = [pairs[0]]
    last_kept_at = datetime.fromisoformat(pairs[0][0])
    checkpoint_gap = CHART_QUOTE_MAX_AGE / 2
    for index in range(1, len(pairs)):
        label, price = pairs[index]
        observed_at = datetime.fromisoformat(label)
        previous_price = pairs[index - 1][1]
        next_price = pairs[index + 1][1] if index + 1 < len(pairs) else None
        changed = abs(price - previous_price) >= 0.005
        ends_flat_run = next_price is None or abs(next_price - price) >= 0.005
        confirms_freshness = observed_at - last_kept_at >= checkpoint_gap
        if changed or ends_flat_run or confirms_freshness:
            out.append((label, price))
            last_kept_at = observed_at
    return out


def _build_chart_payload(
    already,
    detail,
    store_deals,
    launch,
    psn_rows,
    amazon_rows,
    cex_rows,
    ebay_rows,
    *,
    launch_currency="GBP",
    live_store_rows=None,
):
    """Build a truthful, aligned GBP event timeline for Chart.js.

    Each seller is forward-filled only after its first observation. This is a
    standard step-series treatment for independently sampled store prices and
    lets the market average/best lines compare the latest known quote at every
    event instead of averaging only the one store refreshed at that instant.
    ``observed`` marks real checks so the UI can distinguish them from carried
    values. Quotes sharing a seller and timestamp are de-duplicated to the
    cheapest value.
    """
    point_maps: dict[str, dict[str, float]] = defaultdict(dict)
    unavailable_at: dict[str, set[str]] = defaultdict(set)
    historical_count = 0
    live_count = 0

    def add_point(seller, label, amount, currency="GBP") -> bool:
        seller = str(seller or "").strip()[:120]
        gbp = _gbp_point(amount, currency)
        if not seller or gbp is None:
            return False
        previous = point_maps[seller].get(label)
        point_maps[seller][label] = gbp if previous is None else min(previous, gbp)
        return True

    def add_first_row(seller, rows, default_currency="GBP") -> bool:
        added = False
        for row in (rows or [])[:12]:
            if (
                not isinstance(row, dict)
                or row.get("price") is None
                or row.get("in_stock") is False
            ):
                continue
            added = add_point(
                row.get("store_name") or seller,
                now,
                row.get("price"),
                row.get("currency") or default_currency,
            ) or added
        return added

    if already:
        history = list(
            PriceRecord.objects.filter(game=already)
            .select_related("store")
            .only("price", "currency", "recorded_at", "in_stock", "store__name")
            .order_by("-recorded_at")[:CHART_HISTORY_LIMIT]
        )
        history.reverse()
        for h in history:
            seller = str(h.store.name or "").strip()[:120]
            label = h.recorded_at.isoformat()
            if not h.in_stock:
                if seller:
                    # A sold-out check is a tombstone: retain the event so an
                    # earlier price cannot carry through it on the graph.
                    unavailable_at[seller].add(label)
                continue
            if add_point(seller, label, h.price, h.currency):
                historical_count += 1

    # Every live quote belongs to the same final point on the chart.
    now = timezone.now().isoformat()
    detail = detail if isinstance(detail, dict) else {}
    if (
        detail.get("price") is not None
        and detail.get("price_status") in {"paid", "free"}
        and detail.get("in_stock") is not False
    ):
        live_count += int(add_point("Steam", now, detail["price"], detail.get("currency") or "GBP"))
    for deal in (store_deals or [])[:12]:
        if (
            not isinstance(deal, dict)
            or deal.get("price") is None
            or deal.get("in_stock") is False
        ):
            continue
        live_count += int(
            add_point(
                deal.get("store_name"),
                now,
                deal.get("price"),
                deal.get("currency") or "USD",
            )
        )

    default_sources = (
        ("PlayStation Store (UK)", psn_rows, "GBP"),
        ("Amazon UK", amazon_rows, "GBP"),
        ("CeX", cex_rows, "GBP"),
        ("eBay UK", ebay_rows, "GBP"),
    )
    for seller, rows, currency in (*default_sources, *(live_store_rows or [])):
        live_count += int(add_first_row(seller, rows, currency))

    points = {
        seller: _collapse_changes(sorted(by_label.items()))
        for seller, by_label in point_maps.items()
        if by_label
    }
    observed_timestamps = {label for pairs in points.values() for label, _ in pairs}
    for seller in points:
        observed_timestamps.update(unavailable_at.get(seller) or ())
    # Add an explicit boundary when a quote expires. Without this point a
    # stepped line would visually carry a seven-day quote all the way to the
    # next check, even when that check happened months later.
    expiry_timestamps = set()
    if observed_timestamps:
        timeline_end = max(datetime.fromisoformat(label) for label in observed_timestamps)
        for pairs in points.values():
            for index, (label, _) in enumerate(pairs):
                observed_at = datetime.fromisoformat(label)
                expires_at = observed_at + CHART_QUOTE_MAX_AGE
                next_check = (
                    datetime.fromisoformat(pairs[index + 1][0])
                    if index + 1 < len(pairs)
                    else timeline_end
                )
                if expires_at < next_check and expires_at < timeline_end:
                    expiry_timestamps.add(expires_at.isoformat())
    timestamps = sorted(observed_timestamps | expiry_timestamps)

    series: dict[str, list[float | None]] = {}
    observed: dict[str, list[bool]] = {}
    for seller, pairs in points.items():
        by_label = dict(pairs)
        seller_unavailable = unavailable_at.get(seller) or set()
        latest = None
        latest_at = None
        seller_values = []
        seller_observed = []
        for label in timestamps:
            is_tombstone = label in seller_unavailable
            is_observed = label in by_label or is_tombstone
            if is_tombstone:
                latest = None
                latest_at = None
            elif label in by_label:
                latest = by_label[label]
                latest_at = datetime.fromisoformat(label)
            event_at = datetime.fromisoformat(label)
            is_fresh = latest_at is not None and event_at - latest_at < CHART_QUOTE_MAX_AGE
            seller_values.append(latest if is_fresh else None)
            seller_observed.append(is_observed)
        series[seller] = seller_values
        observed[seller] = seller_observed

    average: list[float | None] = []
    best: list[float | None] = []
    for index in range(len(timestamps)):
        values = [values[index] for values in series.values() if values[index] is not None]
        average.append(round(sum(values) / len(values), 2) if values else None)
        best.append(round(min(values), 2) if values else None)

    display_labels = []
    parsed_labels = {}
    for label in timestamps:
        if label == now:
            display_labels.append("Now")
            continue
        parsed = datetime.fromisoformat(label)
        if timezone.is_aware(parsed):
            parsed = timezone.localtime(parsed)
        parsed_labels[label] = parsed
        display_labels.append(parsed.strftime("%d %b %Y, %H:%M"))
    # Separate checks within the same minute instead of rendering ambiguous,
    # repeated x-axis labels. Seconds remain hidden for normal timelines.
    duplicate_labels = Counter(display_labels)
    display_labels = [
        parsed_labels[timestamp].strftime("%d %b %Y, %H:%M:%S")
        if label != "Now" and duplicate_labels[label] > 1
        else label
        for timestamp, label in zip(timestamps, display_labels)
    ]

    launch_gbp = _gbp_point(launch, launch_currency) if launch is not None else None
    if launch_gbp is not None and launch_gbp <= 0:
        launch_gbp = None
    launch_series = [launch_gbp for _ in timestamps]
    sellers = sorted(series.keys(), key=lambda seller: (seller.casefold() != "steam", seller.casefold()))
    valid_best = [value for value in best if value is not None]
    return {
        "labels": display_labels,
        "timestamps": timestamps,
        "series": series,
        "observed": observed,
        "average": average,
        "best": best,
        "launch": launch_series,
        "sellers": sellers,
        "unit": "GBP",
        "change_only": True,
        "snapshot_count": historical_count,
        "live_quote_count": live_count,
        "quote_max_age_days": CHART_QUOTE_MAX_AGE.days,
        "lowest": min(valid_best) if valid_best else None,
        "latest_best": best[-1] if best else None,
        "has_data": bool(timestamps),
    }


def steam_suggest(request):
    # Keep a public endpoint from sending unexpectedly large search strings to Steam.
    q = request.GET.get("q", "").strip()[:150]
    country = request.GET.get("cc", "GB").strip().upper() or "GB"
    if len(q) < 2:
        return JsonResponse({"suggestions": []})
    return JsonResponse({"suggestions": suggest_store(q, country=country, limit=8)})


@require_POST
def track_steam(request, app_id: int):
    """Add (or reactivate) a Steam game without treating an unknown price as free."""
    country = request.GET.get("cc", "GB").strip().upper() or "GB"
    detail = get_app_details(app_id, country=country)
    if not detail:
        return redirect("games:steam_search")

    name = detail["name"]
    slug = _unique_slug(name, app_id)
    existing = Game.objects.filter(steam_app_id=app_id).first()
    defaults = {
        "title": name[:255],
        "slug": existing.slug if existing else slug,
        "platform": Game.Platform.PC,
        "cover_url": detail.get("header_image") or "",
        "is_active": True,
    }
    if existing and existing.launch_price:
        defaults["launch_price"] = existing.launch_price
        defaults["launch_currency"] = existing.launch_currency
        defaults["launch_price_source"] = existing.launch_price_source

    game, _ = Game.objects.update_or_create(steam_app_id=app_id, defaults=defaults)
    ensure_uk_stores()

    status = detail.get("price_status") or "unknown"
    if status != "unknown" and detail.get("price") is not None:
        # A £0 record is legitimate only when Steam explicitly marks the game free.
        store, _ = Store.objects.get_or_create(
            slug="steam",
            defaults={
                "name": "Steam",
                "website": "https://store.steampowered.com",
                "store_type": Store.StoreType.OFFICIAL,
                "country": "GB",
            },
        )
        price = detail["price"]
        original = detail.get("original") or detail.get("list_price")
        discount = detail.get("discount") or None
        record_snapshot(
            game=game,
            store=store,
            price=price,
            currency=detail.get("currency") or "GBP",
            original_price=original,
            discount_percent=discount,
            url=detail.get("url") or "",
            is_physical=False,
            is_used=False,
            in_stock=True,
            notes=name[:255],
        )
    else:
        messages.info(request, "Game tracked, but Steam has no current price to save yet.")

    try:
        from .tasks import refresh_single_game

        refresh_single_game.delay(game.id, country=country)
    except Exception:
        pass

    _bust_ui_caches()
    _log_history(
        request,
        BrowseHistory.Action.TRACK,
        steam_app_id=app_id,
        title=name,
        detail_url=f"/steam/{app_id}/",
    )
    return redirect("games:steam_detail", app_id=app_id)


@require_POST
def untrack_game(request, slug):
    game = get_object_or_404(Game, slug=slug)
    app_id = game.steam_app_id
    game.is_active = False
    game.save(update_fields=["is_active", "updated_at"])
    _bust_ui_caches()
    if app_id:
        return redirect("games:steam_detail", app_id=app_id)
    return redirect("games:home")


def history_page(request):
    items = BrowseHistory.objects.filter(session_key=_session_key(request)).order_by(
        "-created_at"
    )[:100]
    return render(request, "games/history.html", {"items": items})


@login_required
def profile(request):
    watches = list(
        Watch.objects.filter(user=request.user).select_related("game").order_by("-created_at")
    )
    current_by_game = defaultdict(list)
    for offer in latest_store_snapshots(watch.game_id for watch in watches):
        if not offer.in_stock:
            continue
        gbp = to_gbp_or_zero(offer.price, offer.currency)
        # A stored zero is a verified free offer; a positive amount converting
        # to zero means its currency is unknown and must not look like a deal.
        if gbp > 0 or offer.price == 0:
            current_by_game[offer.game_id].append((gbp, offer))
    for watch in watches:
        candidates = current_by_game.get(watch.game_id) or []
        best = min(candidates, key=lambda pair: pair[0]) if candidates else None
        watch.current_price_gbp = best[0] if best else None
        watch.current_offer = best[1] if best else None
        watch.offer_needs_refresh = bool(
            best and quote_needs_refresh(best[1].last_checked_at)
        )
        watch.target_hit = bool(
            best and watch.target_price is not None and best[0] <= watch.target_price
        )
        watch.target_gap = (
            best[0] - watch.target_price
            if best and watch.target_price is not None and best[0] > watch.target_price
            else None
        )
    tracked = list(Game.objects.filter(is_active=True).only("title", "slug", "steam_app_id", "cover_url").order_by("title")[:50])
    alerts = list(
        PriceAlert.objects.filter(watch__user=request.user)
        .select_related("watch__game")
        .order_by("-created_at")[:20]
    )
    unsent_alerts = sum(1 for a in alerts if not a.is_sent)
    return render(
        request,
        "games/profile.html",
        {
            "tracked": tracked,
            "watches": watches,
            "alerts": alerts,
            "unsent_alerts": unsent_alerts,
        },
    )


def game_compare(request, slug):
    game = get_object_or_404(Game, slug=slug, is_active=True)
    if game.steam_app_id:
        return redirect("games:steam_detail", app_id=game.steam_app_id)
    # PriceRecord is append-only history.  Render only each store's newest,
    # purchasable quote so an expired £5 sale cannot beat a current £10 offer.
    prices = [
        price
        for price in latest_store_snapshots([game.id])
        if price.in_stock and _gbp_point(price.price, price.currency) is not None
    ]
    for price in prices:
        # Model instances can safely carry presentation-only metadata; this
        # avoids another query and keeps the 24-hour warning logic shared.
        price.needs_refresh = quote_needs_refresh(price.last_checked_at)
    prices.sort(
        key=lambda price: (
            _gbp_point(price.price, price.currency),
            price.store.name.casefold(),
        )
    )
    lowest = prices[0] if prices else None
    chart = _build_chart_payload(
        game,
        {},
        [],
        game.launch_price,
        [],
        [],
        [],
        [],
        launch_currency=game.launch_currency or "GBP",
    )
    price_insights = build_price_insights(chart)
    return render(
        request,
        "games/compare.html",
        {
            "game": game,
            "prices": prices,
            "lowest": lowest,
            "change": None,
            "retail_baseline": float(game.launch_price) if game.launch_price else None,
            "siblings": [],
            "history_count": chart["snapshot_count"],
            "chart_data": chart,
            "price_insights": price_insights,
            "has_chart": chart["has_data"],
            "watched": None,
        },
    )


def _redirect_after_watch(game: Game, destination: str = ""):
    if destination == "profile":
        return redirect("games:profile")
    if game.steam_app_id:
        return redirect("games:steam_detail", app_id=game.steam_app_id)
    return redirect("games:compare", slug=game.slug)


@login_required
@require_POST
def watch_game(request, slug):
    game = get_object_or_404(Game, slug=slug, is_active=True)
    destination = (request.POST.get("next") or "").strip().lower()
    target_raw = (request.POST.get("target_price") or "").strip()
    target = None
    if target_raw:
        try:
            target = Decimal(target_raw)
            # Decimal accepts values such as NaN/Infinity, which cannot be a
            # meaningful watch threshold or reliably fit in the database.
            if not target.is_finite() or target < 0 or target > Decimal("99999999.99"):
                raise ValueError
        except Exception:
            messages.error(request, "Target price must be a finite zero or positive number.")
            return _redirect_after_watch(game, destination)
    Watch.objects.update_or_create(
        user=request.user,
        game=game,
        defaults={"target_price": target},
    )
    if target is None:
        messages.success(request, f"Watching {game.title}.")
    else:
        messages.success(request, f"Watching {game.title} — alert under £{target}.")
    return _redirect_after_watch(game, destination)


@login_required
@require_POST
def unwatch_game(request, slug):
    game = get_object_or_404(Game, slug=slug, is_active=True)
    Watch.objects.filter(user=request.user, game=game).delete()
    messages.info(request, f"Stopped watching {game.title}.")
    destination = (request.POST.get("next") or "").strip().lower()
    return _redirect_after_watch(game, destination)


@login_required
@require_POST
def clear_alerts(request):
    PriceAlert.objects.filter(watch__user=request.user, is_sent=False).update(
        is_sent=True, sent_at=timezone.now()
    )
    messages.info(request, "Price alerts marked as read.")
    return redirect("games:profile")
