"""
Currency normalisation to GBP.

open.er-api.com/v6/latest/GBP returns: 1 GBP = rate[CODE] units of CODE.
So foreign → GBP is: amount / rate[CODE].

FALLBACK_GBP_RATES stores multipliers: foreign * rate = GBP.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

from django.conf import settings

from .cache import cached

# Multipliers: amount_foreign * rate ≈ GBP
FALLBACK_GBP_RATES = {
    "GBP": Decimal("1.0000"),
    "USD": Decimal("0.7900"),
    "EUR": Decimal("0.8500"),
    "CAD": Decimal("0.5800"),
    "AUD": Decimal("0.5200"),
    "JPY": Decimal("0.00550"),
}

_FX_CACHE_KEY = "fx:rates:gbp:v2"
_FX_TIMEOUT = 24 * 60 * 60


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
        out: dict[str, Decimal] = {"GBP": Decimal("1.0000")}
        for code, rate in rates.items():
            try:
                rdec = Decimal(str(rate))
                if rdec <= 0:
                    continue
                # 1 GBP = rdec foreign → 1 foreign = 1/rdec GBP
                out[code.upper()] = (Decimal("1") / rdec).quantize(
                    Decimal("0.000001"), rounding=ROUND_HALF_UP
                )
            except (InvalidOperation, TypeError, ValueError):
                continue
        return out if len(out) > 1 else FALLBACK_GBP_RATES
    except Exception:
        return FALLBACK_GBP_RATES


def gbp_rates() -> dict[str, Decimal]:
    return cached(_FX_CACHE_KEY, _fetch_gbp_rates, timeout=_FX_TIMEOUT)


def to_gbp(amount: Decimal | int | float | str, currency: str = "GBP") -> Decimal | None:
    try:
        value = Decimal(str(amount))
    except Exception:
        return None
    currency = (currency or getattr(settings, "DEFAULT_CURRENCY", "GBP") or "GBP").upper()
    if currency == "GBP":
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    rate = gbp_rates().get(currency)
    if not rate:
        rate = FALLBACK_GBP_RATES.get(currency)
    if not rate:
        return None
    return (value * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def to_gbp_or_zero(amount: Decimal | int | float | str, currency: str = "GBP") -> Decimal:
    return to_gbp(amount, currency) or Decimal("0.00")
