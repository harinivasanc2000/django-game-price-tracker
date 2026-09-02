"""
Lightweight deal prediction / scoring from public price signals only.

Not financial advice. Heuristic scores from:
  - % under launch / list
  - Steam discount %
  - gap between official and third-party
  - daily market-low insight already calculated for the price graph
"""

from __future__ import annotations

from typing import Any

from .models import Game


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
    price_insights: dict[str, Any] | None = None,
) -> dict[str, Any]:
    signals: list[str] = []
    drop_score = 0
    buy_score = 50

    current_offer = best_offer_gbp if best_offer_gbp is not None else steam_price_gbp
    under_launch = _pct_under(current_offer, launch_gbp)
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

    if (
        best_offer_kind == "third-party"
        and best_offer_gbp is not None
        and steam_price_gbp is not None
        and steam_price_gbp > 0
    ):
        gap = steam_price_gbp - best_offer_gbp
        if gap > 5:
            signals.append(
                f"Keyshop ~£{gap:.2f} cheaper than Steam — weigh risk vs savings."
            )
            buy_score -= 5
        elif gap > 0:
            signals.append("Keyshop only slightly cheaper than official — official often safer.")

    # Reuse the query-free, daily-debiased graph summary. The previous version
    # performed a second history query and could compare two different stores.
    insight = price_insights or {}
    versus_typical = insight.get("vs_typical_percent") if insight.get("has_data") else None
    if isinstance(versus_typical, (int, float)):
        if versus_typical >= 15:
            buy_score += 10
            drop_score -= 5
            signals.append(f"Current best is ~{versus_typical}% below the recorded median.")
        elif versus_typical <= -10:
            buy_score -= 5
            drop_score += 10
            signals.append(f"Current best is ~{abs(versus_typical)}% above the recorded median.")
        else:
            drop_score += 5
            signals.append("Current best is close to the recorded median.")

    drop_score = max(0, min(100, drop_score + 40))
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
