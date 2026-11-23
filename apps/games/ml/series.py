"""Turn one product's price history into booster rows. Store-agnostic."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from apps.games.ml.booster import FEATURE_NAMES, StumpBooster
from apps.games.ml.calendar_events import days_until_cap

DROP_FRACTION = 0.20
HORIZON_DAYS = 30


def _as_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def feature_row(
    *,
    on: date,
    price: float,
    reference: float | None,
    previous_drop_on: date | None,
    price_14d_ago: float | None,
    stock_trend: float = 0.0,
) -> list[float]:
    """One numeric row in FEATURE_NAMES order."""
    discount = 0.0
    under = 0.0
    if reference and reference > 0 and price > 0:
        under = (1 - price / reference) * 100
        discount = max(0.0, under)
    if previous_drop_on is None:
        since_drop = 365.0
    else:
        since_drop = float(min(365, max(0, (on - previous_drop_on).days)))
    days_promo, _label, inside = days_until_cap(on)
    change = 0.0
    if price_14d_ago and price_14d_ago > 0 and price > 0:
        change = (price - price_14d_ago) / price_14d_ago * 100
    assert len(FEATURE_NAMES) == 7
    return [
        discount,
        under,
        since_drop,
        float(days_promo),
        float(inside),
        change,
        stock_trend,
    ]


def walk_forward_rows(points: list[dict]) -> tuple[list[list[float]], list[int]]:
    """Label is 1 when a later point inside 30 days is at least 20% cheaper."""
    rows: list[list[float]] = []
    labels: list[int] = []
    if len(points) < 4:
        return rows, labels
    last_drop: date | None = None
    for index, point in enumerate(points):
        on = point["date"]
        price = float(point["price"])
        if price <= 0:
            continue
        future = [
            later
            for later in points[index + 1 :]
            if later["date"] <= on + timedelta(days=HORIZON_DAYS)
        ]
        if not future:
            continue
        cheapest = min(float(later["price"]) for later in future)
        label = 1 if cheapest <= price * (1 - DROP_FRACTION) else 0
        ago = on - timedelta(days=14)
        older = [p for p in points[:index] if p["date"] <= ago]
        price_then = float(older[-1]["price"]) if older else None
        rows.append(
            feature_row(
                on=on,
                price=price,
                reference=point.get("reference"),
                previous_drop_on=last_drop,
                price_14d_ago=price_then,
                stock_trend=float(point.get("stock_trend") or 0),
            )
        )
        labels.append(label)
        if index > 0 and price <= float(points[index - 1]["price"]) * (1 - 0.08):
            last_drop = on
    return rows, labels


def fit_drop_model(points: list[dict]) -> tuple[StumpBooster | None, list[float] | None]:
    """Fit on labelled history. The latest point is 'today' and is not a training row."""
    if len(points) < 6:
        return None, None
    history = points[:-1]
    rows, labels = walk_forward_rows(history)
    today = _today_row(points)
    if len(rows) < 6 or len(set(labels)) < 2:
        return None, today
    model = StumpBooster().fit(rows, labels)
    if not model.stumps and model.n_rows == 0:
        return None, today
    return model, today


def _today_row(points: list[dict]) -> list[float]:
    today = points[-1]
    last_drop = None
    for index in range(1, len(points)):
        if float(points[index]["price"]) <= float(points[index - 1]["price"]) * 0.92:
            last_drop = points[index]["date"]
    ago = today["date"] - timedelta(days=14)
    older = [p for p in points[:-1] if p["date"] <= ago]
    price_then = float(older[-1]["price"]) if older else None
    return feature_row(
        on=today["date"],
        price=float(today["price"]),
        reference=today.get("reference"),
        previous_drop_on=last_drop,
        price_14d_ago=price_then,
        stock_trend=float(today.get("stock_trend") or 0),
    )
