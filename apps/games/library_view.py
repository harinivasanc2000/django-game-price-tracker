"""Private owned-game checklist and PS4 deal shortlist."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import re

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from .home_view import _safe_home_payload
from .models import Game, OwnedGame


STARTER_PURCHASES = (
    ("God of War (2018)", Decimal("8.00")),
    ("Batman: Arkham Knight", Decimal("6.00")),
    ("Assassin's Creed Valhalla", Decimal("6.00")),
)
MAX_PURCHASE_PRICE = Decimal("99999999.99")


def _title_key(title: str) -> str:
    """Match editions safely while ignoring a trailing year/platform label."""
    text = re.sub(r"\b(?:19|20)\d{2}\b", " ", str(title or "").casefold())
    text = re.sub(r"\bps\s*4\b|\bplaystation\s*4\b", " ", text)
    return " ".join(re.findall(r"[a-z0-9]+", text))


def _purchase_price(raw: str) -> Decimal | None:
    try:
        value = Decimal(str(raw or "").strip())
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not value.is_finite() or value < 0 or value > MAX_PURCHASE_PRICE:
        return None
    return value.quantize(Decimal("0.01"))


def _purchase_date(raw: str):
    if not raw:
        return None
    try:
        value = date.fromisoformat(raw)
    except ValueError:
        return None
    return value if value <= date.today() else None


@login_required
@require_GET
def library(request):
    owned = list(OwnedGame.objects.filter(user=request.user))
    owned_keys = {_title_key(item.title) for item in owned}
    payload = _safe_home_payload(Game.Platform.PS4)
    recommendations = [
        row
        for row in (payload.get("console_deals") or [])
        if _title_key(row.get("title", "")) not in owned_keys
    ][:8]
    total = sum((item.purchase_price for item in owned), Decimal("0"))
    return render(
        request,
        "games/library.html",
        {
            "owned_games": owned,
            "owned_count": len(owned),
            "completed_count": sum(item.completed for item in owned),
            "spent_total": total,
            "recommendations": recommendations,
            "default_location": owned[0].location if owned and owned[0].location else "Glasgow",
            "wide_layout": True,
        },
    )


@login_required
@require_POST
def add_owned_game(request):
    title = " ".join((request.POST.get("title") or "").split())[:255]
    price = _purchase_price(request.POST.get("purchase_price"))
    raw_date = (request.POST.get("purchased_on") or "").strip()
    purchased_on = _purchase_date(raw_date)
    if not title or price is None or (raw_date and purchased_on is None):
        messages.error(request, "Enter a title, a valid GBP price, and a non-future date.")
        return redirect("games:library")

    OwnedGame.objects.update_or_create(
        user=request.user,
        title=title,
        platform=Game.Platform.PS4,
        defaults={
            "purchase_price": price,
            "currency": "GBP",
            "retailer": " ".join((request.POST.get("retailer") or "").split())[:120],
            "location": " ".join((request.POST.get("location") or "").split())[:120],
            "purchased_on": purchased_on,
            "notes": " ".join((request.POST.get("notes") or "").split())[:255],
        },
    )
    messages.success(request, f"Saved {title} to your PS4 checklist.")
    return redirect("games:library")


@login_required
@require_POST
def add_starter_purchases(request):
    created = 0
    for title, price in STARTER_PURCHASES:
        _, was_created = OwnedGame.objects.get_or_create(
            user=request.user,
            title=title,
            platform=Game.Platform.PS4,
            defaults={
                "purchase_price": price,
                "currency": "GBP",
                "retailer": "CeX",
                "location": "Glasgow",
            },
        )
        created += int(was_created)
    messages.success(request, f"Added {created} CeX purchase{'s' if created != 1 else ''}.")
    return redirect("games:library")


@login_required
@require_POST
def toggle_owned_game(request, pk: int):
    item = get_object_or_404(OwnedGame, pk=pk, user=request.user)
    item.completed = not item.completed
    item.save(update_fields=["completed", "updated_at"])
    return redirect("games:library")


@login_required
@require_POST
def delete_owned_game(request, pk: int):
    item = get_object_or_404(OwnedGame, pk=pk, user=request.user)
    title = item.title
    item.delete()
    messages.info(request, f"Removed {title} from your library.")
    return redirect("games:library")
