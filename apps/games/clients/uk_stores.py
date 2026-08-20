"""
UK local / marketplace sources.

Public product search only (BeautifulSoup):
  - product title, price, public rating aggregates, product link
  - never personal seller PII

Facebook Marketplace / social: search URL only (login wall).
Many sites block bots → always return search_url for click-through.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
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
            "note": "Buy / sell used discs",
            "url": f"https://uk.webuy.com/search?stext={qe}",
        },
        {
            "name": "GAME UK",
            "kind": "retail",
            "note": "High-street & online",
            "url": f"https://www.game.co.uk/en/search?q={qe}",
        },
        {
            "name": "Argos",
            "kind": "retail",
            "note": "UK retail",
            "url": f"https://www.argos.co.uk/search/{quote(q)}/",
        },
        {
            "name": "Currys",
            "kind": "retail",
            "note": "Electronics & games",
            "url": f"https://www.currys.co.uk/search?q={qe}",
        },
        {
            "name": "Amazon UK",
            "kind": "marketplace",
            "note": "New & marketplace",
            "url": f"https://www.amazon.co.uk/s?k={qe}&i=videogames",
        },
        {
            "name": "eBay UK",
            "kind": "marketplace",
            "note": "Auction & Buy It Now",
            "url": f"https://www.ebay.co.uk/sch/i.html?_nkw={qe}&_sacat=139973",
        },
        {
            "name": "Smyths Toys",
            "kind": "retail",
            "note": "Often strong on boxed games",
            "url": f"https://www.smythstoys.com/uk/en-gb/search/?text={qe}",
        },
        {
            "name": "Facebook Marketplace",
            "kind": "marketplace",
            "note": "Local pickup — open in browser (no auto-scrape)",
            "url": f"https://www.facebook.com/marketplace/search/?query={qe}",
        },
        {
            "name": "Gumtree",
            "kind": "marketplace",
            "note": "UK classifieds",
            "url": f"https://www.gumtree.com/search?search_category=games&q={qe}",
        },
        {
            "name": "X / Twitter",
            "kind": "social",
            "note": "Deal chatter",
            "url": f"https://x.com/search?q={quote_plus(q + ' game deal OR sale')}&f=live",
        },
        {
            "name": "Reddit",
            "kind": "social",
            "note": "Community deals",
            "url": f"https://www.reddit.com/search/?q={qe}&type=link",
        },
    ]


def _empty(url: str) -> dict[str, Any]:
    return {"results": [], "blocked": True, "search_url": url}


def _safe(fn, *args, **kwargs) -> dict[str, Any]:
    try:
        return fn(*args, **kwargs)
    except Exception:
        return {"results": [], "blocked": True, "search_url": kwargs.get("url") or ""}


def _try_cex_uncached(title: str, platform: str = "", limit: int = 6) -> dict[str, Any]:
    q = platform_query(title, platform)
    url = f"https://uk.webuy.com/search?stext={quote_plus(q)}"
    out: dict[str, Any] = {"results": [], "blocked": False, "search_url": url}
    html, _ = fetch_html(url)
    if not html:
        return _empty(url)

    soup = soup_from(html)
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
            href = url
            id_m = re.search(r'"boxId"\s*:\s*"?([0-9]+)"?', text[m.start() : m.start() + 800])
            if id_m:
                href = f"https://uk.webuy.com/product-detail?id={id_m.group(1)}"
            row = product_row(
                name=m.group(1), price=price, store_name="CeX", url=href, is_used=True
            )
            if row:
                out["results"].append(row)
            if len(out["results"]) >= limit:
                return out

    if not out["results"]:
        for card in soup.select("[class*='product'], [class*='search-product'], .superbox")[: limit + 8]:
            name_el = card.find(["h2", "h3", "a"], class_=re.compile(r"name|title", re.I))
            if not name_el:
                name_el = card.find("a", href=True)
            name = name_el.get_text(" ", strip=True) if name_el else ""
            price_el = card.find(string=re.compile(r"£\s*[0-9]"))
            if not price_el:
                price_el = card.find(class_=re.compile(r"price", re.I))
            price = parse_money(
                price_el if isinstance(price_el, str) else (price_el.get_text() if price_el else "")
            )
            href = url
            if name_el and getattr(name_el, "name", None) == "a" and name_el.get("href"):
                href = urljoin(url, name_el["href"])
            row = product_row(name=name, price=price, store_name="CeX", url=href, is_used=True)
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
        return _empty("")
    return cached(
        f"cex:v2:{title.lower()}:{platform}",
        lambda: _try_cex_uncached(title, platform=platform, limit=limit),
        timeout=1800,
    )


def _try_ebay_uncached(title: str, platform: str = "", limit: int = 6) -> dict[str, Any]:
    q = platform_query(title, platform)
    url = f"https://www.ebay.co.uk/sch/i.html?_nkw={quote_plus(q)}&_sacat=139973"
    out: dict[str, Any] = {"results": [], "blocked": False, "search_url": url}
    html, _ = fetch_html(url)
    if not html:
        return _empty(url)

    soup = soup_from(html)
    for item in soup.select("li.s-item, .s-item"):
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
        return _empty("")
    return cached(
        f"ebay:v2:{title.lower()}:{platform}",
        lambda: _try_ebay_uncached(title, platform=platform, limit=limit),
        timeout=1800,
    )


def _try_game_uk_uncached(title: str, platform: str = "", limit: int = 6) -> dict[str, Any]:
    q = platform_query(title, platform)
    url = f"https://www.game.co.uk/en/search?q={quote_plus(q)}"
    out: dict[str, Any] = {"results": [], "blocked": False, "search_url": url}
    html, _ = fetch_html(url)
    if not html:
        return _empty(url)
    soup = soup_from(html)
    for card in soup.select("article, .product, [data-product], .product-card, li")[: limit + 20]:
        a = card.find("a", href=True)
        if not a:
            continue
        href = urljoin(url, a["href"])
        name_el = card.find(["h2", "h3", "span"], class_=re.compile(r"name|title", re.I))
        name = (name_el or a).get_text(" ", strip=True) if (name_el or a) else ""
        if len(name) < 3:
            continue
        price_el = card.find(class_=re.compile(r"price", re.I))
        price = parse_money(price_el.get_text() if price_el else "")
        if price is None:
            price = parse_money(card.get_text(" ", strip=True))
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
        return _empty("")
    return cached(
        f"gameuk:v2:{title.lower()}:{platform}",
        lambda: _try_game_uk_uncached(title, platform=platform, limit=limit),
        timeout=1800,
    )


def _try_argos_uncached(title: str, platform: str = "", limit: int = 6) -> dict[str, Any]:
    q = platform_query(title, platform)
    url = f"https://www.argos.co.uk/search/{quote(q)}/"
    out: dict[str, Any] = {"results": [], "blocked": False, "search_url": url}
    html, _ = fetch_html(url)
    if not html:
        return _empty(url)
    soup = soup_from(html)
    for script in soup.find_all("script"):
        text = script.string or ""
        if '"name"' not in text or '"price"' not in text:
            continue
        for m in re.finditer(
            r'"name"\s*:\s*"([^"]{5,120})".{0,300}?"price"\s*:\s*([0-9]+(?:\.[0-9]+)?)',
            text,
            re.DOTALL,
        ):
            try:
                price = Decimal(m.group(2))
            except InvalidOperation:
                continue
            name = m.group(1)
            if "argos" in name.lower():
                continue
            row = product_row(name=name, price=price, store_name="Argos", url=url)
            if row:
                out["results"].append(row)
            if len(out["results"]) >= limit:
                return out

    for card in soup.select("[data-test='component-product-card'], article, .ProductCard")[: limit + 10]:
        a = card.find("a", href=True)
        name_el = card.find(["h2", "h3", "span"], class_=re.compile(r"title|name", re.I))
        name = (name_el or a).get_text(" ", strip=True) if (name_el or a) else ""
        price_el = card.find(class_=re.compile(r"price", re.I))
        price = parse_money(price_el.get_text() if price_el else card.get_text(" ", strip=True))
        href = urljoin(url, a["href"]) if a else url
        row = product_row(name=name, price=price, store_name="Argos", url=href)
        if row:
            out["results"].append(row)
        if len(out["results"]) >= limit:
            break

    if not out["results"]:
        out["blocked"] = True
    return out


def try_argos(title: str, platform: str = "", limit: int = 6) -> dict[str, Any]:
    title = (title or "").strip()
    if not title:
        return _empty("")
    return cached(
        f"argos:v1:{title.lower()}:{platform}",
        lambda: _try_argos_uncached(title, platform=platform, limit=limit),
        timeout=1800,
    )


def _try_currys_uncached(title: str, platform: str = "", limit: int = 6) -> dict[str, Any]:
    q = platform_query(title, platform)
    url = f"https://www.currys.co.uk/search?q={quote_plus(q)}"
    out: dict[str, Any] = {"results": [], "blocked": False, "search_url": url}
    html, _ = fetch_html(url)
    if not html:
        return _empty(url)
    soup = soup_from(html)
    for card in soup.select(
        "[data-component='product-card'], .product, article, [class*='ProductCard']"
    )[: limit + 12]:
        a = card.find("a", href=True)
        name_el = card.find(["h2", "h3", "span"], class_=re.compile(r"name|title", re.I))
        name = (name_el or a).get_text(" ", strip=True) if (name_el or a) else ""
        price_el = card.find(class_=re.compile(r"price", re.I))
        price = parse_money(price_el.get_text() if price_el else card.get_text(" ", strip=True))
        href = urljoin(url, a["href"]) if a else url
        row = product_row(name=name, price=price, store_name="Currys", url=href)
        if row:
            out["results"].append(row)
        if len(out["results"]) >= limit:
            break
    if not out["results"]:
        for script in soup.find_all("script", type="application/ld+json"):
            text = script.string or ""
            for m in re.finditer(
                r'"name"\s*:\s*"([^"]+)".{0,400}?"price"\s*:\s*"?([0-9.]+)',
                text,
                re.DOTALL,
            ):
                try:
                    price = Decimal(m.group(2))
                except InvalidOperation:
                    continue
                row = product_row(name=m.group(1), price=price, store_name="Currys", url=url)
                if row:
                    out["results"].append(row)
                if len(out["results"]) >= limit:
                    break
    if not out["results"]:
        out["blocked"] = True
    return out


def try_currys(title: str, platform: str = "", limit: int = 6) -> dict[str, Any]:
    title = (title or "").strip()
    if not title:
        return _empty("")
    return cached(
        f"currys:v1:{title.lower()}:{platform}",
        lambda: _try_currys_uncached(title, platform=platform, limit=limit),
        timeout=1800,
    )


def fetch_uk_physical_bundle(title: str, platform: str = "", limit: int = 5) -> dict[str, Any]:
    title = (title or "").strip()
    links = uk_search_links(title, platform)

    def _wrap(fn):
        def run():
            try:
                return fn(title, platform, limit)
            except Exception:
                return {"results": [], "blocked": True, "search_url": ""}

        return run

    with ThreadPoolExecutor(max_workers=6) as pool:
        f_cex = pool.submit(_wrap(try_cex_search))
        f_ebay = pool.submit(_wrap(try_ebay_uk))
        f_game = pool.submit(_wrap(try_game_uk))
        f_argos = pool.submit(_wrap(try_argos))
        f_currys = pool.submit(_wrap(try_currys))
        cex = f_cex.result()
        ebay = f_ebay.result()
        game = f_game.result()
        argos = f_argos.result()
        currys = f_currys.result()

    return {
        "cex": cex,
        "ebay": ebay,
        "game": game,
        "argos": argos,
        "currys": currys,
        "uk_links": links,
    }
