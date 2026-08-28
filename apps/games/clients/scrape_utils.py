"""
Polite public HTML helpers (BeautifulSoup).

Project rule
------------
Sites **without a documented public API** (GAME, Argos, Currys, Smyths,
eBay, Amazon, MusicMagpie, …) are scraped with **BeautifulSoup** on their
public search pages only.

If an unofficial/API path is **blocked** (403, captcha, empty) → fall back
to BS4 HTML of the same public search URL. Soft-fail keeps `search_url`.

Scope (strict):
  - Only pages reachable via a normal public *product search*
  - Extract product title, price, public rating aggregates, product URL
  - Do NOT collect personal seller identity, addresses, phone, email, etc.
"""

from __future__ import annotations

import re
import math
import threading
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
DEFAULT_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    # Do not advertise Brotli explicitly: ``requests`` can only decode it when
    # an optional Brotli package is installed.  gzip/deflate work everywhere.
    "Accept-Encoding": "gzip, deflate",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "DNT": "1",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Connection": "keep-alive",
}

_PARSER = "html.parser"
try:
    import lxml  # noqa: F401

    _PARSER = "lxml"
except ImportError:
    pass

_SESSION_STATE = threading.local()


def _session() -> requests.Session:
    """Return one pooled session per worker thread.

    UK sources are fetched concurrently.  A requests.Session owns mutable
    cookie/header state, so sharing one session between every worker can race.
    Thread-local sessions retain connection pooling without that risk.
    """
    session = getattr(_SESSION_STATE, "session", None)
    if session is None:
        s = requests.Session()
        s.headers.update(DEFAULT_HEADERS)
        retry = Retry(
            total=1,
            connect=1,
            read=0,
            backoff_factor=0.2,
            status_forcelist=(502, 503, 504),
            allowed_methods=frozenset(["GET"]),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(pool_connections=12, pool_maxsize=12, max_retries=retry)
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        _SESSION_STATE.session = s
        session = s
    return session


def normalise_public_url(
    url: str | None,
    *,
    base_url: str = "",
    allowed_hosts: Iterable[str] = (),
) -> str:
    """Return a safe absolute HTTP(S) URL, or an empty string.

    Scraped hrefs are untrusted input.  This rejects script/data schemes,
    credentials, control characters and cross-site links when a retailer host
    allow-list is supplied.  Fragments are removed because they are not needed
    for product navigation and make otherwise-identical rows harder to dedupe.
    """
    raw = str(url or "").strip()
    if not raw or any(ord(char) < 32 for char in raw):
        return ""

    candidate = urljoin(base_url, raw) if base_url else raw
    try:
        parts = urlsplit(candidate)
        host = (parts.hostname or "").rstrip(".").lower()
        if parts.scheme.lower() not in {"http", "https"} or not host:
            return ""
        if parts.username is not None or parts.password is not None:
            return ""
        allowed = tuple(str(item).lower().lstrip(".") for item in allowed_hosts if item)
        if allowed and not any(host == item or host.endswith(f".{item}") for item in allowed):
            return ""
        return urlunsplit((parts.scheme.lower(), parts.netloc, parts.path or "/", parts.query, ""))
    except (TypeError, ValueError):
        return ""


def fetch_html(
    url: str,
    timeout: float = 9,
    *,
    referer: str | None = None,
) -> tuple[str | None, int]:
    """GET public HTML for BS4. Soft-fail on block/captcha/empty."""
    safe_url = normalise_public_url(url)
    if not safe_url:
        return None, 0
    headers = {}
    if referer:
        headers["Referer"] = referer
    try:
        r = _session().get(safe_url, timeout=timeout, headers=headers or None)
    except requests.RequestException:
        return None, 0
    if r.status_code != 200 or not r.text or len(r.text) < 300 or len(r.content) > 6_000_000:
        return None, r.status_code
    low = r.text[:8000].lower()
    if any(
        marker in low
        for marker in (
            "cf-chl-captcha",
            "cf-chl-widget",
            "g-recaptcha-response",
            "hcaptcha-response",
        )
    ):
        return None, r.status_code
    if "captcha" in low and ("robot" in low or "are you a human" in low):
        return None, r.status_code
    if "access denied" in low and ("cloudflare" in low or "akamai" in low):
        return None, r.status_code
    return r.text, r.status_code


def fetch_json(
    url: str,
    *,
    params: dict | None = None,
    timeout: float = 9,
    headers: dict | None = None,
) -> tuple[Any | None, int]:
    """GET JSON. On failure callers should fall back to fetch_html + BS4."""
    safe_url = normalise_public_url(url)
    if not safe_url:
        return None, 0
    h = {
        "Accept": "application/json, text/plain, */*",
        "User-Agent": UA,
        "Accept-Language": "en-GB,en;q=0.9",
    }
    if headers:
        h.update(headers)
    try:
        r = _session().get(safe_url, params=params, timeout=timeout, headers=h)
    except requests.RequestException:
        return None, 0
    if r.status_code != 200:
        return None, r.status_code
    try:
        return r.json(), r.status_code
    except ValueError:
        return None, r.status_code


def soup_from(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, _PARSER)


def parse_money(text: str | None, *, require_currency: bool = False) -> Decimal | None:
    """Extract a GBP price without confusing years, ratings or RRP values.

    Currency-marked values win.  When a card contains both the live price and a
    crossed-out ``was``/``RRP`` price, the reference amount is ignored.  Bare
    numbers remain supported for dedicated price fields and JSON payloads; card
    text fallbacks should pass ``require_currency=True``.
    """
    if not text:
        return None
    cleaned = re.sub(r"\s+", " ", str(text).replace("\xa0", " ")).strip()

    # Never silently report a foreign-currency amount as GBP.
    if ("€" in cleaned or re.search(r"\bEUR\b", cleaned, re.I)) and "£" not in cleaned:
        return None
    if "$" in cleaned and "£" not in cleaned and not re.search(r"\bGBP\b", cleaned, re.I):
        return None

    amount = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?"
    marked_pattern = re.compile(
        rf"(?:£|\bGBP\s*)\s*(?P<amount>{amount})|(?P<after>{amount})\s*\bGBP\b",
        re.I,
    )
    candidates: list[tuple[int, Decimal]] = []
    for match in marked_pattern.finditer(cleaned):
        raw = match.group("amount") or match.group("after") or ""
        try:
            value = Decimal(raw.replace(",", ""))
        except InvalidOperation:
            continue
        if not value.is_finite() or value < 0:
            continue
        prefix = cleaned[max(0, match.start() - 18) : match.start()].lower()
        suffix = cleaned[match.end() : match.end() + 16].lower()
        is_reference = bool(re.search(r"(?:was|rrp|save|saving)\s*$", prefix))
        is_instalment = bool(re.match(r"\s*(?:/|per)\s*(?:month|week)", suffix))
        if not is_reference and not is_instalment:
            candidates.append((match.start(), value))

    if candidates:
        # Retail markup normally places the current sale value after the old
        # amount; reference prices were removed above, so the last is safest.
        return candidates[-1][1]
    if require_currency:
        return None

    # Dedicated price elements and JSON values commonly contain a bare number.
    bare = re.fullmatch(rf"\s*({amount})\s*", cleaned)
    if not bare:
        return None
    try:
        value = Decimal(bare.group(1).replace(",", ""))
        return value if value.is_finite() and value >= 0 else None
    except InvalidOperation:
        return None


def parse_rating(text: str | None) -> float | None:
    if not text:
        return None
    normalized = text.replace(",", ".")
    m = re.search(r"\b([0-5](?:\.\d{1,2})?)\s*(?:out of|/)\s*5\b", normalized, re.I)
    if not m:
        m = re.search(r"\b([0-5](?:\.\d{1,2})?)\s*(?:stars?|★)\b", normalized, re.I)
    if not m:
        return None
    try:
        v = float(m.group(1))
        return v if math.isfinite(v) and 0 <= v <= 5 else None
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
    name = re.sub(r"\s+", " ", str(name or "")).strip()[:200]
    try:
        amount = Decimal(str(price))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not name or not amount.is_finite() or amount < 0 or amount > Decimal("1000000"):
        return None
    safe_url = normalise_public_url(url)
    currency = str(currency or "GBP").strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", currency):
        currency = "GBP"
    row: dict[str, Any] = {
        "name": name,
        "price": amount,
        "currency": currency,
        "url": safe_url,
        "store_name": re.sub(r"\s+", " ", str(store_name or "")).strip()[:80],
        "is_used": bool(is_used),
    }
    try:
        rating_value = float(rating) if rating is not None else None
    except (TypeError, ValueError):
        rating_value = None
    if rating_value is not None and math.isfinite(rating_value) and 0 <= rating_value <= 5:
        row["rating"] = rating_value
    return row


def extract_ld_json_products(soup: BeautifulSoup, limit: int = 20) -> list[dict[str, Any]]:
    """Pull products from Product/ItemList JSON-LD, including nested graphs.

    Retailers vary between ``price``, ``lowPrice`` and offer lists.  The walker
    handles those shapes, prefers GBP offers, records stock state, and dedupes
    repeated Product nodes commonly emitted for mobile and desktop markup.
    """
    import json

    try:
        limit = max(1, min(int(limit), 100))
    except (TypeError, ValueError):
        limit = 20

    found: list[dict[str, Any]] = []
    seen_products: set[tuple[str, str, str]] = set()

    def iter_nodes(value: Any, depth: int = 0):
        if depth > 12:
            return
        if isinstance(value, dict):
            yield value
            for nested in value.values():
                yield from iter_nodes(nested, depth + 1)
        elif isinstance(value, list):
            for nested in value:
                yield from iter_nodes(nested, depth + 1)

    def offer_candidates(value: Any) -> list[dict[str, Any]]:
        if isinstance(value, dict):
            nested = value.get("offers")
            if nested and not (value.get("price") or value.get("lowPrice")):
                return offer_candidates(nested)
            return [value]
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        return []

    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text() or ""
        if not raw or "price" not in raw.lower():
            continue
        raw = raw.strip().removeprefix("<!--").removesuffix("-->").strip().rstrip(";")
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue

        for node in iter_nodes(data):
            raw_types = node.get("@type") or ""
            types = raw_types if isinstance(raw_types, list) else [raw_types]
            if not any(str(item).lower() == "product" for item in types):
                continue

            name = re.sub(r"\s+", " ", str(node.get("name") or "")).strip()
            if not name:
                continue
            offers = offer_candidates(node.get("offers") or node.get("priceSpecification") or {})
            if not offers and node.get("price") is not None:
                offers = [node]

            # UK pages occasionally include several regional offers; prefer GBP
            # while still accepting an unlabelled price from a UK retailer.
            offers.sort(
                key=lambda offer: 0
                if str(offer.get("priceCurrency") or "").upper() == "GBP"
                else (1 if not offer.get("priceCurrency") else 2)
            )
            for offer in offers:
                currency = str(offer.get("priceCurrency") or node.get("priceCurrency") or "GBP").upper()
                if currency not in {"", "GBP"}:
                    continue
                raw_price = offer.get("price")
                if raw_price is None:
                    raw_price = offer.get("lowPrice")
                price = parse_money(str(raw_price)) if raw_price is not None else None
                if price is None:
                    continue
                url = str(offer.get("url") or node.get("url") or "")
                key = (name.casefold(), str(price), url)
                if key in seen_products:
                    break
                seen_products.add(key)
                availability = str(offer.get("availability") or "").lower()
                item: dict[str, Any] = {
                    "name": name,
                    "price": str(price),
                    "url": url,
                    "currency": currency or "GBP",
                }
                if availability:
                    item["in_stock"] = not any(
                        marker in availability
                        for marker in ("outofstock", "soldout", "discontinued")
                    )
                found.append(item)
                break
            if len(found) >= limit:
                return found
    return found
