"""
Core views: tracking, profile, history, autocomplete, chart helpers.

Home / search / detail live in dedicated modules (home_view, search_view,
views_steam_detail) — keep this file focused on shared actions.
"""
from __future__ import annotations

import json
from collections import defaultdict
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
from .views_best_deals import best_deals  # noqa: F401

HISTORY_MAX_PER_SESSION = 100
HISTORY_PRUNE_INTERVAL = timezone.timedelta(hours=24)
HISTORY_PRUNE_MARK = timezone.timedelta(days=60)


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
    bust("tracked_drawer:v1")
    bust("home:cards:v2")


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
    v = to_gbp(amount, currency)
    return float(v) if v is not None else None


def _collapse_changes(pairs: list[tuple[str, float]]) -> list[tuple[str, float]]:
    if not pairs:
        return []
    out = [pairs[0]]
    for lab, price in pairs[1:]:
        if abs(price - out[-1][1]) >= 0.005:
            out.append((lab, price))
    return out


def _build_chart_payload(already, detail, store_deals, launch, psn_rows, amazon_rows, cex_rows, ebay_rows):
    """Return chronologically ordered GBP series for Chart.js.

    ISO timestamps are used as internal keys so prices from several stores at
    the same minute cannot overwrite one another before display labels exist.
    """
    points: dict[str, list[tuple[str, float]]] = defaultdict(list)

    if already:
        history = list(
            PriceRecord.objects.filter(game=already)
            .select_related("store")
            .order_by("recorded_at")[:200]
        )
        for h in history:
            label = h.recorded_at.isoformat()
            gbp = _gbp_point(h.price, h.currency)
            if gbp is not None:
                points[h.store.name].append((label, gbp))

    # Every live quote belongs to the same final point on the chart.
    now = timezone.now().isoformat()
    if detail.get("price") is not None and detail.get("price_status") == "paid":
        g = _gbp_point(detail["price"], detail.get("currency") or "GBP")
        if g is not None:
            points["Steam"].append((now, g))
    for deal in store_deals[:8]:
        g = _gbp_point(deal["price"], deal.get("currency") or "USD")
        if g is not None:
            points[deal["store_name"]].append((now, g))
    for row in psn_rows[:1]:
        if float(row.get("price") or 0) > 0:
            g = _gbp_point(row["price"], "GBP")
            if g is not None:
                points["PlayStation Store (UK)"].append((now, g))
    for row in amazon_rows[:1]:
        g = _gbp_point(row["price"], "GBP")
        if g is not None:
            points["Amazon UK"].append((now, g))
    for row in cex_rows[:1]:
        g = _gbp_point(row["price"], "GBP")
        if g is not None:
            points["CeX"].append((now, g))
    for row in ebay_rows[:1]:
        g = _gbp_point(row["price"], "GBP")
        if g is not None:
            points["eBay UK"].append((now, g))

    for seller in list(points.keys()):
        points[seller] = _collapse_changes(points[seller])

    labels = sorted({lab for pairs in points.values() for lab, _ in pairs})
    if not labels:
        labels = [now]

    series: dict[str, list] = {}
    for seller, pairs in points.items():
        by_lab = {lab: price for lab, price in pairs}
        series[seller] = [by_lab.get(lab) for lab in labels]

    avg = []
    for i, _ in enumerate(labels):
        vals = [series[s][i] for s in series if series[s][i] is not None]
        avg.append(round(sum(vals) / len(vals), 2) if vals else None)
    avg_pairs = [(labels[i], avg[i]) for i in range(len(labels)) if avg[i] is not None]
    avg_collapsed = _collapse_changes(avg_pairs)
    if avg_collapsed:
        labels = [p[0] for p in avg_collapsed]
        avg = [p[1] for p in avg_collapsed]
        for seller in series:
            by_lab = {lab: price for lab, price in points.get(seller, [])}
            series[seller] = [by_lab.get(lab) for lab in labels]

    display_labels = [
        "Now" if label == now else datetime.fromisoformat(label).strftime("%d %b %H:%M")
        for label in labels
    ]
    launch_series = [launch for _ in labels] if launch is not None else [None for _ in labels]
    sellers = sorted(series.keys(), key=lambda s: (s != "Steam", s.lower()))
    return {
        "labels": display_labels,
        "series": series,
        "average": avg,
        "launch": launch_series,
        "sellers": sellers,
        "unit": "GBP",
        "change_only": True,
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
        PriceRecord.objects.create(
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
    prices = list(
        PriceRecord.objects.filter(game=game)
        .select_related("store")
        .order_by("price", "-recorded_at")[:50]
    )

    def _gbp(p):
        return to_gbp_or_zero(p.price, p.currency)

    prices.sort(key=_gbp)
    lowest = prices[0] if prices else None
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
            "history_count": 0,
            "chart_labels": "[]",
            "chart_values": "[]",
            "chart_stores": "[]",
            "watched": None,
        },
    )


def _redirect_after_watch(game: Game):
    if game.steam_app_id:
        return redirect("games:steam_detail", app_id=game.steam_app_id)
    return redirect("games:compare", slug=game.slug)


@login_required
@require_POST
def watch_game(request, slug):
    game = get_object_or_404(Game, slug=slug, is_active=True)
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
            return _redirect_after_watch(game)
    Watch.objects.update_or_create(
        user=request.user,
        game=game,
        defaults={"target_price": target},
    )
    if target is None:
        messages.success(request, f"Watching {game.title}.")
    else:
        messages.success(request, f"Watching {game.title} — alert under £{target}.")
    return _redirect_after_watch(game)


@login_required
@require_POST
def unwatch_game(request, slug):
    game = get_object_or_404(Game, slug=slug, is_active=True)
    Watch.objects.filter(user=request.user, game=game).delete()
    messages.info(request, f"Stopped watching {game.title}.")
    return _redirect_after_watch(game)


@login_required
@require_POST
def clear_alerts(request):
    PriceAlert.objects.filter(watch__user=request.user, is_sent=False).update(
        is_sent=True, sent_at=timezone.now()
    )
    messages.info(request, "Price alerts marked as read.")
    return redirect("games:profile")
