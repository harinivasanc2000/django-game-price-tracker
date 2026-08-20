"""
Lightweight deal prediction / scoring from public price signals only.

Not financial advice. Heuristic scores from:
  - % under launch / list
  - Steam discount %
  - gap between official and third-party
  - recent PriceRecord trend if tracked
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.utils import timezone

from .fx import to_gbp_or_zero
from .models import Game, PriceRecord


def _pct_under(current: float | None, baseline: float | None) -> int | None:
    if current is None or baseline is None or baseline <= 0:
        return None
    return int(round((1 - current / baseline) * 100))


def predict_deal(
    *,
    title: str = "",
    steam_price_gbp: float | None = None,
    steam_discount: int | None = None,
    launch_gbp: float | None = None,
    best_offer_gbp: float | None = None,
    best_offer_kind: str | None = None,
    game: Game | None = None,
) -> dict[str, Any]:
    """Return human-readable prediction + numeric scores."""
    signals: list[str] = []
    drop_score = 0  # 0–100 likelihood that waiting could still save money
    buy_score = 50  # 0–100 "reasonable to buy now"

    under_launch = _pct_under(best_offer_gbp or steam_price_gbp, launch_gbp)
    if under_launch is not None:
        if under_launch >= 50:
            buy_score += 25
            drop_score -= 15
            signals.append(f"~{under_launch}% under launch reference — historically strong.")
        elif under_launch >= 25:
            buy_score += 12
            signals.append(f"~{under_launch}% under launch — solid sale territory.")
        elif under_launch >= 10:
            buy_score += 5
            drop_score += 10
            signals.append(f"Only ~{under_launch}% under launch — deeper sales often appear later.")
        elif under_launch < 0:
            drop_score += 20
            buy_score -= 10
            signals.append("Above launch reference — unusual; double-check edition/region.")

    disc = steam_discount or 0
    if disc >= 60:
        buy_score += 15
        drop_score -= 10
        signals.append(f"Steam shows -{disc}% — major platform sale.")
    elif disc >= 30:
        buy_score += 8
        signals.append(f"Steam -{disc}% mid-tier discount.")
    elif disc > 0:
        drop_score += 12
        signals.append(f"Steam only -{disc}% — seasonal sales often go deeper.")
    elif steam_price_gbp and launch_gbp and abs(steam_price_gbp - launch_gbp) < 0.5:
        drop_score += 18
        signals.append("Near full price on Steam — waiting for a sale is often rewarded.")

    if best_offer_kind == "third-party" and best_offer_gbp and steam_price_gbp:
        gap = steam_price_gbp - best_offer_gbp
        if gap > 5:
            signals.append(
                f"Keyshop ~£{gap:.2f} cheaper than Steam — weigh risk vs savings."
            )
            buy_score -= 5  # risk penalty
        elif gap > 0:
            signals.append("Keyshop only slightly cheaper than official — official often safer.")

    # Trend from stored snapshots
    if game:
        since = timezone.now() - timezone.timedelta(days=14)
        rows = list(
            PriceRecord.objects.filter(game=game, recorded_at__gte=since)
            .order_by("recorded_at")[:40]
        )
        if len(rows) >= 3:
            first = float(to_gbp_or_zero(rows[0].price, rows[0].currency))
            last = float(to_gbp_or_zero(rows[-1].price, rows[-1].currency))
            if first > 0 and last > 0:
                change = (last - first) / first * 100
                if change <= -8:
                    buy_score += 10
                    signals.append(f"Tracked price fell ~{abs(int(change))}% in 2 weeks.")
                elif change >= 8:
                    drop_score -= 5
                    signals.append("Tracked price rose recently — may re-discount later.")
                else:
                    drop_score += 5
                    signals.append("Tracked price mostly flat recently.")

    drop_score = max(0, min(100, drop_score + 40))  # baseline mid
    buy_score = max(0, min(100, buy_score))

    if buy_score >= 70:
        verdict = "Good time to buy (heuristic)"
    elif buy_score >= 50:
        verdict = "Reasonable deal — or wait for a deeper sale"
    else:
        verdict = "Likely better to wait for a sale"

    if drop_score >= 65:
        wait_note = "Higher chance of a further drop (especially seasonal Steam sales)."
    elif drop_score >= 45:
        wait_note = "Mixed — further discounts possible but not guaranteed."
    else:
        wait_note = "Further big drops less likely from current signals."

    return {
        "verdict": verdict,
        "wait_note": wait_note,
        "buy_score": buy_score,
        "drop_likelihood": drop_score,
        "under_launch_pct": under_launch,
        "signals": signals[:6],
        "disclaimer": (
            "Heuristic only from public prices — not a guarantee. "
            "Always confirm on the store before buying."
        ),
    }
