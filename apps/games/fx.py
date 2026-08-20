"""
Currency normalisation.

Prices arrive in several currencies (GBP from Steam UK / PSN / UK shops,
USD from CheapShark). To compare them fairly we convert everything to a
single target currency using approximate public FX rates.

Rates are fetched at most once per day from the free
open.er-api.com/v6/latest endpoint and cached; if the network is
unavailable a small built-in fallback table is used so the site never
breaks.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings

from .cache import cached

# Approximate fixed fallbacks (GBP base) — only used if the live fetch
# fails and the value is not cached. Good enough for deal comparison.
FALLBACK_GBP_RATES = {
    "GBP": Decimal("1.0000"),
    "USD": Decimal("0.7900"),
    "EUR": Decimal("0.8500"),
    "CAD": Decimal("0.5800"),
    "AUD": Decimal("0.5200"),
    "JPY": Decimal("0.00550"),
}

_FX_CACHE_KEY = "fx:rates:gbp"
_FX_TIMEOUT = 24 * 60 * 60  # 1 day


def _fetch_gbp_rates() -> dict[str, Decimal]:
    try:
        import requests

        r = requests.get(
            "https://open.er-api.com/v6/latest/GBP",
            timeout=6,
            headers={"User-Agent": "GamePriceTracker/0.1 (polite)"},
        )
        r.raise_for_status()
        payload = r.json()
        rates = payload.get("rates") or {}
        if not rates:
            return FALLBACK_GBP_RATES
        return {
            code: Decimal(str(rate))
            for code, rate in rates.items()
            if isinstance(rate, (int, float)) and rate > 0
        }
    except Exception:  # noqa: BLE001 — offline is not fatal
        return FALLBACK_GBP_RATES


def gbp_rates() -> dict[str, Decimal]:
    """Map currency code -> rate to convert that currency into GBP."""
    return cached(_FX_CACHE_KEY, _fetch_gbp_rates, timeout=_FX_TIMEOUT)


def to_gbp(amount: Decimal | int | float | str, currency: str = "GBP") -> Decimal | None:
    """Convert `amount` to Decimal GBP. Returns None if unparseable."""
    try:
        value = Decimal(str(amount))
    except Exception:  # noqa: BLE001
        return None
    currency = (currency or settings.DEFAULT_CURRENCY).upper()
    if currency == "GBP":
        return value
    rate = gbp_rates().get(currency)
    if not rate:
        return None
    return (value * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def to_gbp_or_zero(amount: Decimal | int | float | str, currency: str = "GBP") -> Decimal:
    """Like `to_gbp` but never None — useful for sort keys."""
    return to_gbp(amount, currency) or Decimal("0.00")
