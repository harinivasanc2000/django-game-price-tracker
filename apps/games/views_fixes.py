"""Safe helpers used by steam_detail."""
from __future__ import annotations

from typing import Any

from .fx import to_gbp_or_zero
from .prediction import predict_deal


def build_prediction(detail: dict, live_offers: list, launch, catalog) -> dict[str, Any]:
    try:
        steam_gbp = None
        if detail.get("price_status") == "paid" and detail.get("price") is not None:
            steam_gbp = float(to_gbp_or_zero(detail["price"], detail.get("currency") or "GBP"))
        best_gbp = float(live_offers[0]["price_gbp"]) if live_offers else steam_gbp
        best_kind = live_offers[0].get("kind") if live_offers else "official"
        return predict_deal(
            title=detail.get("name") or "",
            steam_price_gbp=steam_gbp,
            steam_discount=detail.get("discount") or 0,
            launch_gbp=float(launch) if launch else None,
            best_offer_gbp=best_gbp,
            best_offer_kind=best_kind,
            game=catalog,
        )
    except Exception:
        return {
            "verdict": "Outlook unavailable",
            "wait_note": "Could not score this title right now.",
            "buy_score": 50,
            "drop_likelihood": 50,
            "under_launch_pct": None,
            "signals": [],
            "disclaimer": "Heuristic only — confirm prices on the store.",
        }
