"""
Polite public HTML helpers (BeautifulSoup).

Scope (strict):
  - Only pages reachable via a normal public *product search*
  - Extract product title, price, public rating aggregates, product URL
  - Do NOT collect personal seller identity, addresses, phone, email, etc.
  - Seller *rating score* / feedback % is OK when shown publicly on the listing card

Always respect blocks (403/captcha) → return empty + search_url fallback.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

import requests
from bs4 import BeautifulSoup

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
DEFAULT_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}


def fetch_html(url: str, timeout: int = 12) -> tuple[str | None, int]:
    try:
        r = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
    except requests.RequestException:
        return None, 0
    if r.status_code != 200 or not r.text or len(r.text) < 400:
        return None, r.status_code
    # common bot walls
    low = r.text.lower()
    if "captcha" in low and "robot" in low:
        return None, r.status_code
    return r.text, r.status_code


def soup_from(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def parse_money(text: str | None) -> Decimal | None:
    if not text:
        return None
    cleaned = text.replace(",", "").replace("\xa0", " ")
    m = re.search(r"(?:£|\$|EUR)?\s*([0-9]+(?:\.[0-9]{1,2})?)", cleaned)
    if not m:
        return None
    try:
        return Decimal(m.group(1))
    except InvalidOperation:
        return None


def parse_rating(text: str | None) -> float | None:
    """Public star rating e.g. '4.5 out of 5'."""
    if not text:
        return None
    m = re.search(r"([0-5](?:\.[0-9])?)\s*(?:out of|/)?\s*5?", text.replace(",", "."))
    if not m:
        return None
    try:
        v = float(m.group(1))
        return v if 0 <= v <= 5 else None
    except ValueError:
        return None


def product_row(
    *,
    name: str,
    price: Decimal | None,
    currency: str = "GBP",
    url: str = "",
    store_name: str = "",
    rating: float | None = None,
    is_used: bool = False,
) -> dict[str, Any] | None:
    name = (name or "").strip()[:200]
    if not name or price is None or price < 0:
        return None
    row: dict[str, Any] = {
        "name": name,
        "price": price,
        "currency": currency,
        "url": url,
        "store_name": store_name,
        "is_used": is_used,
    }
    if rating is not None:
        row["rating"] = rating  # public aggregate only
    return row
