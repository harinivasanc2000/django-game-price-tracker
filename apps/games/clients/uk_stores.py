"""
UK local / marketplace sources.

Public product search only (BeautifulSoup):
  - product title, price, public rating aggregates, product link
  - never personal seller PII (name/address/phone)

Many sites block datacenter IPs → always provide search_url fallback.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import quote_plus, quote, urljoin

from apps.games.cache import cached
from apps.games.clients.scrape_utils import (
    fetch_html,
    parse_money,
    parse_rating,
    product_row,
    soup_from,
)


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
            "note": "Auction & Buy It Now — public seller *rating* only",
            "url": f"https://www.ebay.co.uk/sch/i.html?_nkw={qe}&_sacat=139973",
        },
        {
            "name": "Facebook Marketplace",
            "kind": "marketplace",
            "note": "Link only — no scrape (login wall)",
            "url": f"https://www.facebook.com/marketplace/search/?query={qe}",
        },
        {
            "name": "X / Twitter search",
            "kind": "social",
            "note": "Deal chatter links only",
            "url": f"https://x.com/search?q={quote_plus(q + ' game deal OR sale')}&f=live",
        },
        {
            "name": "Reddit deals",
            "kind": "social",
            "note": "Community deal posts",
            "url": f"https://www.reddit.com/search/?q={qe}&type=link",
        },
    ]


def _try_cex_uncached(title: str, platform: str = "", limit: int = 6) -> dict[str, Any]:
    q = platform_query(title, platform)
    url = f"https://uk.webuy.com/search?stext={quote_plus(q)}"
    out: dict[str, Any] = {"results": [], "blocked": False, "search_url": url}

    html, status = fetch_html(url)
    if not html:
        out["blocked"] = True
        return out

    soup = soup_from(html)
    # Prefer structured JSON in page if present
    for script in soup.find_all("script"):
        text = script.string or script.get_text() or ""
        if "sellPrice" not in text or "boxName" not in text:
            continue
        for m in re.finditer(
            r'"boxName"\s*:\s*"([^"]+)".{0,500}?"sellPrice"\s*:\s*([0-9.]+)',
            text,
            re.DOTALL,
        ):
            try:
                price = Decimal(m.group(2))
            except InvalidOperation:
                continue
            row = product_row(
                name=m.group(1),
                price=price,
                store_name="CeX",
                url=url,
                is_used=True,
            )
            if row:
                out["results"].append(row)
            if len(out["results"]) >= limit:
                return out

    # BS4 card fallback
    if not out["results"]:
        for card in soup.select("[class*='product'], [class*='search-product'], .superbox")[: limit + 8]:
            name_el = card.find(["h2", "h3", "a"], class_=re.compile(r"name|title", re.I))
            if not name_el:
                name_el = card.find("a")
            name = name_el.get_text(" ", strip=True) if name_el else ""
            price_el = card.find(string=re.compile(r"£\s*[0-9]"))
            if not price_el:
                price_el = card.find(class_=re.compile(r"price", re.I))
            price = parse_money(price_el if isinstance(price_el, str) else (price_el.get_text() if price_el else ""))
            href = ""
            if name_el and name_el.name == "a" and name_el.get("href"):
                href = urljoin(url, name_el["href"])
            row = product_row(name=name, price=price, store_name="CeX", url=href or url, is_used=True)
            if row:
                out["results"].append(row)
            if len(out["results"]) >= limit:
                break

    if not out["results"]:
        out["blocked"] = True
    return out


def try_cex_search(title: str, platform: str = "", limit: int = 6) -> dict[str, Any]:
    title = (title or "").strip()
    if not title:
        return {"results": [], "blocked": True, "search_url": ""}
    return cached(
        f"cex:bs4:{title.lower()}:{platform}",
        lambda: _try_cex_uncached(title, platform=platform, limit=limit),
        timeout=1800,
    )


def _try_ebay_uncached(title: str, platform: str = "", limit: int = 6) -> dict[str, Any]:
    q = platform_query(title, platform)
    url = f"https://www.ebay.co.uk/sch/i.html?_nkw={quote_plus(q)}&_sacat=139973"
    out: dict[str, Any] = {"results": [], "blocked": False, "search_url": url}

    html, _ = fetch_html(url)
    if not html:
        out["blocked"] = True
        return out

    soup = soup_from(html)
    items = soup.select("li.s-item, .s-item")
    for item in items:
        title_el = item.select_one(".s-item__title")
        if not title_el:
            continue
        name = title_el.get_text(" ", strip=True)
        if not name or name.lower().startswith("shop on ebay"):
            continue
        price_el = item.select_one(".s-item__price")
        price = parse_money(price_el.get_text() if price_el else "")
        link_el = item.select_one("a.s-item__link")
        href = link_el["href"] if link_el and link_el.get("href") else url
        # Public feedback % only — not seller personal identity
        rating = None
        rating_el = item.select_one(".s-item__seller-info-text, .x-star-rating")
        if rating_el:
            rating = parse_rating(rating_el.get_text(" ", strip=True))
        row = product_row(
            name=name,
            price=price,
            store_name="eBay UK",
            url=href.split("?")[0],
            rating=rating,
            is_used=True,
        )
        if row:
            out["results"].append(row)
        if len(out["results"]) >= limit:
            break

    if not out["results"]:
        out["blocked"] = True
    return out


def try_ebay_uk(title: str, platform: str = "", limit: int = 6) -> dict[str, Any]:
    title = (title or "").strip()
    if not title:
        return {"results": [], "blocked": True, "search_url": ""}
    return cached(
        f"ebay:bs4:{title.lower()}:{platform}",
        lambda: _try_ebay_uncached(title, platform=platform, limit=limit),
        timeout=1800,
    )


def _try_game_uk_uncached(title: str, platform: str = "", limit: int = 6) -> dict[str, Any]:
    """GAME.co.uk public search — product cards only."""
    q = platform_query(title, platform)
    url = f"https://www.game.co.uk/en/search?q={quote_plus(q)}"
    out: dict[str, Any] = {"results": [], "blocked": False, "search_url": url}
    html, _ = fetch_html(url)
    if not html:
        out["blocked"] = True
        return out
    soup = soup_from(html)
    for card in soup.select("article, .product, [data-product], .product-card")[: limit + 10]:
        a = card.find("a", href=True)
        name_el = card.find(["h2", "h3", "span"], class_=re.compile(r"name|title", re.I))
        name = (name_el or a).get_text(" ", strip=True) if (name_el or a) else ""
        price_el = card.find(class_=re.compile(r"price", re.I))
        price = parse_money(price_el.get_text() if price_el else "")
        href = urljoin(url, a["href"]) if a else url
        row = product_row(name=name, price=price, store_name="GAME UK", url=href)
        if row:
            out["results"].append(row)
        if len(out["results"]) >= limit:
            break
    if not out["results"]:
        out["blocked"] = True
    return out


def try_game_uk(title: str, platform: str = "", limit: int = 6) -> dict[str, Any]:
    title = (title or "").strip()
    if not title:
        return {"results": [], "blocked": True, "search_url": ""}
    return cached(
        f"gameuk:bs4:{title.lower()}:{platform}",
        lambda: _try_game_uk_uncached(title, platform=platform, limit=limit),
        timeout=1800,
    )
