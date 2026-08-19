"""
Amazon UK public search — best-effort HTML parse.

Amazon often returns WAF/captcha (HTTP 202) to datacenter IPs.
When HTML is available we extract asin, title, price from public search markup.
Always returns a search_url fallback.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import quote_plus

import requests

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def search_url(title: str, extra: str = "") -> str:
    q = quote_plus(f"{title} {extra}".strip())
    return f"https://www.amazon.co.uk/s?k={q}&i=videogames"


def search_amazon_uk(title: str, extra: str = "", limit: int = 8) -> dict[str, Any]:
    """
    Returns { results: [...], blocked: bool, search_url: str }
    """
    url = search_url(title, extra)
    out: dict[str, Any] = {"results": [], "blocked": False, "search_url": url}

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-GB,en;q=0.9",
    }
    try:
        r = requests.get(url, headers=headers, timeout=12)
    except requests.RequestException:
        out["blocked"] = True
        return out

    if r.status_code != 200 or not r.text or "a-price-whole" not in r.text:
        out["blocked"] = True
        return out

    html = r.text
    # Split roughly by result cards
    chunks = re.split(r'data-component-type="s-search-result"', html)[1:]
    results = []
    for chunk in chunks[: limit + 5]:
        asin_m = re.search(r'data-asin="([A-Z0-9]{10})"', chunk)
        if not asin_m:
            asin_m = re.search(r'data-asin="([A-Z0-9]{10})"', "data-asin=" + chunk[:200])
        asin = asin_m.group(1) if asin_m else ""

        title_m = re.search(
            r'class="a-size-medium a-color-base a-text-normal"[^>]*>([^<]+)',
            chunk,
        )
        if not title_m:
            title_m = re.search(
                r'class="a-size-base-plus a-color-base a-text-normal"[^>]*>([^<]+)',
                chunk,
            )
        if not title_m:
            title_m = re.search(r'<h2[^>]*>\s*<a[^>]*>\s*<span[^>]*>([^<]+)', chunk)
        name = (title_m.group(1).strip() if title_m else "")[:200]
        if not name:
            continue

        whole_m = re.search(r'class="a-price-whole">([^<]+)', chunk)
        frac_m = re.search(r'class="a-price-fraction">([^<]+)', chunk)
        if not whole_m:
            continue
        whole = whole_m.group(1).replace(",", "").replace(".", "").strip()
        frac = frac_m.group(1).strip() if frac_m else "00"
        try:
            price = Decimal(f"{whole}.{frac}")
        except (InvalidOperation, ValueError):
            continue

        product_url = (
            f"https://www.amazon.co.uk/dp/{asin}" if asin else url
        )
        results.append(
            {
                "name": name,
                "price": price,
                "currency": "GBP",
                "asin": asin,
                "url": product_url,
                "store_name": "Amazon UK",
            }
        )
        if len(results) >= limit:
            break

    out["results"] = results
    out["blocked"] = len(results) == 0
    return out
