"""
Polite public HTML helpers (BeautifulSoup).

Scope (strict):
  - Only pages reachable via a normal public *product search*
  - Extract product title, price, public rating aggregates, product URL
  - Do NOT collect personal seller identity, addresses, phone, email, etc.

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
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
DEFAULT_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
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

_SESSION: requests.Session | None = None


def _session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
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
        # Larger pool — UK bundle fires 6 parallel GETs
        adapter = HTTPAdapter(pool_connections=12, pool_maxsize=12, max_retries=retry)
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        _SESSION = s
    return _SESSION


def fetch_html(
    url: str,
    timeout: float = 9,
    *,
    referer: str | None = None,
) -> tuple[str | None, int]:
    """GET public HTML. Soft-fail on block/captcha/empty."""
    headers = {}
    if referer:
        headers["Referer"] = referer
    try:
        r = _session().get(url, timeout=timeout, headers=headers or None)
    except requests.RequestException:
        return None, 0
    if r.status_code != 200 or not r.text or len(r.text) < 300:
        return None, r.status_code
    low = r.text[:8000].lower()
    if "captcha" in low and ("robot" in low or "are you a" in low or "cf-" in low):
        return None, r.status_code
    if "access denied" in low and "cloudflare" in low:
        return None, r.status_code
    return r.text, r.status_code


def fetch_json(
    url: str,
    *,
    params: dict | None = None,
    timeout: float = 9,
    headers: dict | None = None,
) -> tuple[Any | None, int]:
    """GET JSON (CeX boxes API etc.). Soft-fail."""
    h = {
        "Accept": "application/json, text/plain, */*",
        "User-Agent": UA,
        "Accept-Language": "en-GB,en;q=0.9",
    }
    if headers:
        h.update(headers)
    try:
        r = _session().get(url, params=params, timeout=timeout, headers=h)
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


def parse_money(text: str | None) -> Decimal | None:
    if not text:
        return None
    cleaned = text.replace(",", "").replace("\xa0", " ").replace("\u00a3", "£")
    m = re.search(r"(?:£|\$|EUR|€)?\s*([0-9]+(?:\.[0-9]{1,2})?)", cleaned)
    if not m:
        return None
    try:
        return Decimal(m.group(1))
    except InvalidOperation:
        return None


def parse_rating(text: str | None) -> float | None:
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
        row["rating"] = rating
    return row


def extract_ld_json_products(soup: BeautifulSoup, limit: int = 20) -> list[dict[str, str]]:
    """Pull name/price pairs from application/ld+json Product / ItemList blobs."""
    import json

    found: list[dict[str, str]] = []
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text() or ""
        if not raw or "price" not in raw.lower():
            continue
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            # Regex fallback already used by callers; skip broken JSON here
            continue
        nodes = data if isinstance(data, list) else [data]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            graph = node.get("@graph")
            if isinstance(graph, list):
                nodes.extend(graph)
            typ = node.get("@type") or ""
            types = typ if isinstance(typ, list) else [typ]
            if "Product" in types or typ == "Product":
                name = node.get("name") or ""
                offers = node.get("offers") or {}
                if isinstance(offers, list) and offers:
                    offers = offers[0]
                price = ""
                if isinstance(offers, dict):
                    price = str(offers.get("price") or "")
                if name and price:
                    found.append({"name": str(name), "price": price, "url": str(node.get("url") or "")})
            if "ItemList" in types:
                for el in node.get("itemListElement") or []:
                    if not isinstance(el, dict):
                        continue
                    item = el.get("item") or el
                    if not isinstance(item, dict):
                        continue
                    name = item.get("name") or ""
                    offers = item.get("offers") or {}
                    if isinstance(offers, list) and offers:
                        offers = offers[0]
                    price = ""
                    if isinstance(offers, dict):
                        price = str(offers.get("price") or "")
                    if name and price:
                        found.append(
                            {
                                "name": str(name),
                                "price": price,
                                "url": str(item.get("url") or ""),
                            }
                        )
            if len(found) >= limit:
                return found
    return found
