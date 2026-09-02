"""Small, deterministic price insights derived from the existing chart payload.

The calculation deliberately performs no database or network work. Both game
detail views already build an aligned GBP history for the chart, so reusing it
keeps the feature effectively free at request time.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import math
from statistics import median
from typing import Any

from django.utils import timezone


def _timestamp(value: Any) -> datetime | None:
    """Parse one chart timestamp into an aware datetime when possible."""
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def build_price_insights(chart: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    """Summarise the tracker's best-price series without overstating certainty."""
    chart = chart if isinstance(chart, dict) else {}
    reference_time = now or timezone.now()
    if timezone.is_naive(reference_time):
        reference_time = timezone.make_aware(reference_time, timezone.get_current_timezone())
    timed_best: list[tuple[datetime, float]] = []
    for raw_time, raw_price in zip(chart.get("timestamps") or [], chart.get("best") or []):
        try:
            price = float(raw_price)
        except (TypeError, ValueError, OverflowError):
            continue
        observed_at = _timestamp(raw_time)
        if observed_at is not None and math.isfinite(price) and price >= 0:
            timed_best.append((observed_at, price))

    # Use one market-low sample per local calendar day. This prevents a noisy
    # retailer with many checks from dominating the median. Current candidates
    # come from each seller's own latest real check, never a carried graph value.
    daily_best: dict[object, float] = {}
    latest_by_seller: dict[str, tuple[datetime, float]] = {}
    timestamps = chart.get("timestamps") or []
    series = chart.get("series") or {}
    observed = chart.get("observed") or {}
    for index, raw_time in enumerate(timestamps):
        observed_at = _timestamp(raw_time)
        if observed_at is None:
            continue
        local_day = timezone.localtime(observed_at).date()
        for seller, prices in series.items():
            seller_observed = observed.get(seller) or []
            if index >= len(prices) or index >= len(seller_observed) or not seller_observed[index]:
                continue
            try:
                price = float(prices[index])
            except (TypeError, ValueError, OverflowError):
                # An observed null is a sold-out tombstone and ends the older
                # quote for this seller.
                latest_by_seller.pop(seller, None)
                continue
            if math.isfinite(price) and price >= 0:
                daily_best[local_day] = min(daily_best.get(local_day, price), price)
                latest_by_seller[seller] = (observed_at, price)

    freshness_cutoff = reference_time - timedelta(days=7)
    if series:
        fresh_prices = [
            price
            for observed_at, price in latest_by_seller.values()
            if observed_at >= freshness_cutoff
        ]
    else:
        # Backwards-compatible fallback for callers supplying only best/times.
        fresh_prices = [price for observed_at, price in timed_best if observed_at >= freshness_cutoff]
    if not fresh_prices:
        return {"has_data": False}
    current = min(fresh_prices)

    values = list(daily_best.values()) or [price for _observed_at, price in timed_best]
    recorded_low = min(values)
    typical = float(median(values))
    recent_values = [
        price
        for day, price in daily_best.items()
        if day >= timezone.localtime(reference_time - timedelta(days=30)).date()
    ]

    vs_typical = None
    if typical > 0:
        # Positive means today's best is cheaper than the median shown history.
        vs_typical = round(((typical - current) / typical) * 100)

    snapshot_count = max(0, int(chart.get("snapshot_count") or 0))
    seller_count = len(chart.get("sellers") or [])
    day_count = len(daily_best) or len(values)
    if day_count >= 10 and snapshot_count >= 20 and seller_count >= 3:
        confidence = "High"
    elif day_count >= 3 and (snapshot_count >= 6 or seller_count >= 2):
        confidence = "Medium"
    else:
        confidence = "Low"

    if current == 0:
        verdict, tone = "Free now", "excellent"
    elif len(values) < 2:
        verdict, tone = "Building history", "neutral"
    elif current <= recorded_low + 0.005:
        verdict, tone = "Lowest shown", "excellent"
    elif typical > 0 and current <= typical * 0.85:
        verdict, tone = "Great price", "good"
    elif typical > 0 and current <= typical:
        verdict, tone = "Below typical", "good"
    elif typical > 0 and current <= typical * 1.10:
        verdict, tone = "Typical price", "neutral"
    else:
        verdict, tone = "Above typical", "caution"

    return {
        "has_data": True,
        "current": round(current, 2),
        "recorded_low": round(recorded_low, 2),
        "typical": round(typical, 2),
        "low_30d": round(min(recent_values), 2) if recent_values else None,
        "vs_typical_percent": vs_typical,
        "verdict": verdict,
        "tone": tone,
        "confidence": confidence,
        "snapshot_count": snapshot_count,
        "seller_count": seller_count,
        "day_count": day_count,
    }
