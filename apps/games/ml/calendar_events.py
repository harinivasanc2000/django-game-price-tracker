"""Known promo windows. Dates are public retail calendars, not learned."""

from __future__ import annotations

from datetime import date

# (start, end inclusive, label). Digital and physical both feel these weeks.
# Other catalogues can pass their own list into next_promo; this is the games default.
GAME_PROMOS: tuple[tuple[date, date, str], ...] = (
    (date(2025, 11, 28), date(2025, 12, 2), "Black Friday"),
    (date(2025, 12, 18), date(2026, 1, 5), "Steam Winter Sale"),
    (date(2025, 12, 26), date(2026, 1, 2), "Boxing Day sales"),
    (date(2026, 6, 25), date(2026, 7, 9), "Steam Summer Sale"),
    (date(2026, 10, 6), date(2026, 10, 13), "Amazon Prime Big Deal Days"),
    (date(2026, 11, 25), date(2026, 12, 2), "Steam Autumn Sale"),
    (date(2026, 11, 27), date(2026, 12, 1), "Black Friday"),
    (date(2026, 12, 22), date(2027, 1, 5), "Steam Winter Sale"),
    (date(2026, 12, 26), date(2027, 1, 2), "Boxing Day sales"),
    (date(2027, 6, 24), date(2027, 7, 8), "Steam Summer Sale"),
    (date(2027, 11, 26), date(2027, 11, 30), "Black Friday"),
)


def next_promo(
    on: date,
    promos: tuple[tuple[date, date, str], ...] = GAME_PROMOS,
) -> dict | None:
    """Soonest window that has not ended. Inside a window, days_until is 0."""
    best = None
    for start, end, label in promos:
        if end < on:
            continue
        days = 0 if start <= on <= end else (start - on).days
        if best is None or days < best["days_until"]:
            best = {
                "label": label,
                "days_until": days,
                "inside": start <= on <= end,
                "start": start,
                "end": end,
            }
    return best


def days_until_cap(on: date, cap: int = 120) -> tuple[int, str, int]:
    promo = next_promo(on)
    if not promo:
        return cap, "", 0
    return min(promo["days_until"], cap), promo["label"], int(promo["inside"])
