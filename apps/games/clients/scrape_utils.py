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
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
DEFAULT_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Connection": "keep-alive",
}

# Prefer lxml if installed; otherwise stdlib html.parser (no extra install).
_PARSER = "html.parser"
try:
    import lxml  # noqa: F401

    _PARSER = "lxml"
except ImportError:
    pass

# Shared session with connection pooling — fewer TCP handshakes across scrapes.
_SESSION: requests.Session | None = None


def _session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        s = requests.Session()
        s.headers.update(DEFAULT_HEADERS)
        retry = Retry(
            total=1,
            connect=1,
            read=1,
            backoff_factor=0.3,
            status_forcelist=(502, 503, 504),
            allowed_methods=frozenset(["GET"]),
        )
        adapter = HTTPAdapter(pool_connections=8, pool_maxsize=8, max_retries=retry)
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        _SESSION = s
    return _SESSION


def fetch_html(url: str, timeout: int = 10) -> tuple[str | None, int]:
    try:
        r = _session().get(url, timeout=timeout)
    except requests.RequestException:
        return None, 0
    if r.status_code != 200 or not r.text or len(r.text) < 400:
        return None, r.status_code
    low = r.text.lower()
    if "captcha" in low and ("robot" in low or "are you a" in low):
        return None, r.status_code
    return r.text, r.status_code


def soup_from(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, _PARSER)


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
