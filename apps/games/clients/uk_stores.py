"""
UK local / marketplace sources.

Many (CeX API, eBay, GAME) block datacenter IPs with 403/WAF.
We:
  1) Try polite public requests when possible
  2) Always provide official search URLs for the user

Facebook Marketplace is link-only (login wall / ToS — no scraping).
X/Twitter is link-only search for deal chatter + news (no unofficial scrape).
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import quote_plus, quote

import requests

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
HEADERS = {"User-Agent": UA, "Accept-Language": "en-GB,en;q=0.9"}


def _money(text: str) -> Decimal | None:
    m = re.search(r"[£$]?\s*([0-9]+(?:[.,][0-9]{2})?)", text.replace(",", ""))
    if not m:
        return None
    try:
        return Decimal(m.group(1))
    except InvalidOperation:
        return None


def platform_query(title: str, platform: str = "") -> str:
    t = (title or "").strip()
    p = (platform or "").strip().lower()
    hints = {
        "ps4": "PS4",
        "ps5": "PS5",
        "xbox": "Xbox",
        "switch": "Nintendo Switch",
        "pc": "PC",
    }
    if p in hints:
        return f"{t} {hints[p]}"
    return t


def uk_search_links(title: str, platform: str = "") -> list[dict[str, str]]:
    q = platform_query(title, platform)
    qe = quote_plus(q)
    return [
        {
            "name": "CeX",
            "kind": "used-physical",
            "note": "UK second-hand discs & electronics",
            "url": f"https://uk.webuy.com/search?stext={qe}",
        },
        {
            "name": "GAME UK",
            "kind": "retail",
            "note": "High-street & online retail",
            "url": f"https://www.game.co.uk/en/search?q={qe}",
        },
        {
            "name": "Argos",
            "kind": "retail",
            "note": "UK retail",
            "url": f"https://www.argos.co.uk/search/{quote(q)}/",
        },
        {
            "name": "Smyths Toys",
            "kind": "retail",
            "note": "Often competitive on new boxed games",
            "url": f"https://www.smythstoys.com/uk/en-gb/search/?text={qe}",
        },
        {
            "name": "eBay UK",
            "kind": "marketplace",
            "note": "Auction & Buy It Now — check seller ratings",
            "url": f"https://www.ebay.co.uk/sch/i.html?_nkw={qe}&_sacat=139973",
        },
        {
            "name": "Facebook Marketplace",
            "kind": "marketplace",
            "note": "Local pickup — meet safely; no automated prices (login wall)",
            "url": f"https://www.facebook.com/marketplace/search/?query={qe}",
        },
        {
            "name": "X / Twitter search",
            "kind": "social",
            "note": "Deal alerts & chatter (not official prices)",
            "url": f"https://x.com/search?q={quote_plus(q + ' game deal OR sale')}&f=live",
        },
        {
            "name": "Reddit deals",
            "kind": "social",
            "note": "Community deal posts",
            "url": f"https://www.reddit.com/search/?q={qe}&type=link",
        },
    ]


def try_cex_search(title: str, platform: str = "", limit: int = 6) -> dict[str, Any]:
    """Attempt CeX public search page; fall back if blocked."""
    q = platform_query(title, platform)
    url = f"https://uk.webuy.com/search?stext={quote_plus(q)}"
    out: dict[str, Any] = {"results": [], "blocked": False, "search_url": url}

    # API often 403; try HTML search page
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
    except requests.RequestException:
        out["blocked"] = True
        return out

    if r.status_code != 200 or len(r.text) < 500:
        out["blocked"] = True
        return out

    # Best-effort extract from embedded JSON if present
    html = r.text
    for m in re.finditer(
        r'"boxName"\s*:\s*"([^"]+)".{0,400}?"sellPrice"\s*:\s*([0-9.]+)',
        html,
        re.DOTALL,
    ):
        name, price = m.group(1), m.group(2)
        try:
            out["results"].append(
                {
                    "name": name[:200],
                    "price": Decimal(price),
                    "currency": "GBP",
                    "store_name": "CeX",
                    "url": url,
                    "is_used": True,
                }
            )
        except InvalidOperation:
            continue
        if len(out["results"]) >= limit:
            break

    if not out["results"]:
        # price patterns near product cards (fragile)
        prices = re.findall(r"£([0-9]+\.[0-9]{2})", html)
        # without reliable titles, don't invent rows
        out["blocked"] = True
    return out


def try_ebay_uk(title: str, platform: str = "", limit: int = 6) -> dict[str, Any]:
    q = platform_query(title, platform)
    url = f"https://www.ebay.co.uk/sch/i.html?_nkw={quote_plus(q)}&_sacat=139973"
    out: dict[str, Any] = {"results": [], "blocked": False, "search_url": url}
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
    except requests.RequestException:
        out["blocked"] = True
        return out
    if r.status_code != 200 or "s-item__price" not in r.text:
        out["blocked"] = True
        return out

    chunks = re.split(r'class="s-item__wrapper', r.text)[1:]
    for chunk in chunks[: limit + 3]:
        tm = re.search(r'class="s-item__title"[^>]*>\s*(?:<span[^>]*>)?([^<]+)', chunk)
        pm = re.search(r'class="s-item__price"[^>]*>([^<]+)', chunk)
        lm = re.search(r'href="(https://www\.ebay\.co\.uk/itm/[^"?]+)', chunk)
        if not tm or not pm:
            continue
        name = tm.group(1).strip()
        if name.lower().startswith("shop on ebay"):
            continue
        price = _money(pm.group(1))
        if price is None:
            continue
        out["results"].append(
            {
                "name": name[:200],
                "price": price,
                "currency": "GBP",
                "store_name": "eBay UK",
                "url": lm.group(1) if lm else url,
                "is_used": True,
            }
        )
        if len(out["results"]) >= limit:
            break
    if not out["results"]:
        out["blocked"] = True
    return out
