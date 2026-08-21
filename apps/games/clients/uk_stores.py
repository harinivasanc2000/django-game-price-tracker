"""
UK local / marketplace sources — public product search (no login).

BeautifulSoup scrapes + URL-level filters where the site supports them
(e.g. eBay BIN, condition, price band). Soft-fail → search_url always kept.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, wait
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import quote_plus, quote, urljoin

from apps.games.cache import cached
from apps.games.clients.scrape_filters import filter_source_dict, parse_price_bound
from apps.games.clients.scrape_utils import (
    fetch_html,
    parse_money,
    parse_rating,
    product_row,
    soup_from,
)

_ACCESSORY_HINTS = (
    "controller", "dualsense", "dualshock", "gamepad", "headset", "earbud",
    "carry case", "travel case", "charging dock", "charge station", "thumb grip",
    "silicone", "skin cover", "screen protector", "stand only", "mount only",
    "microfibre", "cleaning kit", "battery pack", "power bank",
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


def uk_search_links(
    title: str,
    platform: str = "",
    *,
    min_price: str | Decimal | None = None,
    max_price: str | Decimal | None = None,
    condition: str = "",
) -> list[dict[str, str]]:
    q = platform_query(title, platform)
    qe = quote_plus(q)
    lo = parse_price_bound(str(min_price) if min_price is not None else None)
    hi = parse_price_bound(str(max_price) if max_price is not None else None)
    cond = (condition or "").strip().lower()

    # eBay public filter params (no login)
    ebay = f"https://www.ebay.co.uk/sch/i.html?_nkw={qe}&_sacat=139973&LH_BIN=1&_sop=15"
    if lo is not None:
        ebay += f"&_udlo={lo}"
    if hi is not None:
        ebay += f"&_udhi={hi}"
    if cond == "new":
        ebay += "&LH_ItemCondition=1000"
    elif cond == "used":
        ebay += "&LH_ItemCondition=3000"

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
            "name": "Smyths Toys",
            "kind": "retail",
            "note": "Boxed games / consoles",
            "url": f"https://www.smythstoys.com/uk/en-gb/search/?text={qe}",
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
            "note": "Buy It Now · filtered",
            "url": ebay,
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
    ]


def _empty(url: str) -> dict[str, Any]:
    return {"results": [], "blocked": True, "search_url": url}


def _title_matches(name: str, title: str) -> bool:
    haystack = (name or "").lower()
    ignored = {
        "the", "and", "for", "with", "edition", "game", "ps4", "ps5",
        "xbox", "pc", "switch", "nintendo", "playstation", "sony", "microsoft",
    }
    tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", (title or "").lower())
        if len(token) > 2 and token not in ignored
    ]
    if not tokens:
        return True
    required = 1 if len(tokens) == 1 else 2
    hits = sum(token in haystack for token in tokens)
    if hits < required:
        return False
    if any(h in haystack for h in _ACCESSORY_HINTS) and hits < max(required + 1, 2):
        return False
    return True


def _keep_matching_rows(source: dict[str, Any], title: str) -> dict[str, Any]:
    source = dict(source or {})
    source["results"] = [
        row for row in (source.get("results") or []) if _title_matches(row.get("name", ""), title)
    ]
    if not source["results"]:
        source["blocked"] = True
    return source


def _ebay_search_url(
    title: str,
    platform: str = "",
    *,
    min_price: Decimal | None = None,
    max_price: Decimal | None = None,
    condition: str = "",
) -> str:
    q = platform_query(title, platform)
    # Public filters: category Video Games, Buy It Now, price low→high
    url = (
        f"https://www.ebay.co.uk/sch/i.html?_nkw={quote_plus(q)}"
        f"&_sacat=139973&LH_BIN=1&_sop=15"
    )
    if min_price is not None:
        url += f"&_udlo={min_price}"
    if max_price is not None:
        url += f"&_udhi={max_price}"
    cond = (condition or "").strip().lower()
    if cond == "new":
        url += "&LH_ItemCondition=1000"
    elif cond == "used":
        url += "&LH_ItemCondition=3000"
    return url


def _try_cex_uncached(title: str, platform: str = "", limit: int = 8) -> dict[str, Any]:
    q = platform_query(title, platform)
    url = f"https://uk.webuy.com/search?stext={quote_plus(q)}"
    out: dict[str, Any] = {"results": [], "blocked": False, "search_url": url}
    html, _ = fetch_html(url, timeout=12)
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
                row["condition"] = "used"
                out["results"].append(row)
            if len(out["results"]) >= limit:
                return out

    if not out["results"]:
        for card in soup.select("[class*='product'], [class*='search-product'], .superbox")[: limit + 12]:
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
                row["condition"] = "used"
                out["results"].append(row)
            if len(out["results"]) >= limit:
                break

    if not out["results"]:
        out["blocked"] = True
    return out


def try_cex_search(title: str, platform: str = "", limit: int = 8) -> dict[str, Any]:
    title = (title or "").strip()
    if not title:
        return _empty("")
    return cached(
        f"cex:v4:{title.lower()}:{platform}:{limit}",
        lambda: _try_cex_uncached(title, platform=platform, limit=limit),
        timeout=1800,
    )


def _try_ebay_uncached(
    title: str,
    platform: str = "",
    limit: int = 8,
    *,
    min_price: Decimal | None = None,
    max_price: Decimal | None = None,
    condition: str = "",
) -> dict[str, Any]:
    url = _ebay_search_url(
        title, platform, min_price=min_price, max_price=max_price, condition=condition
    )
    out: dict[str, Any] = {"results": [], "blocked": False, "search_url": url}
    html, _ = fetch_html(url, timeout=12)
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

        # Condition from subtitle / secondary text when present
        subtitle = ""
        sub_el = item.select_one(".SECONDARY_INFO, .s-item__subtitle, .s-item__caption")
        if sub_el:
            subtitle = sub_el.get_text(" ", strip=True)
        blob = f"{name} {subtitle}".lower()
        is_used = any(
            x in blob for x in ("pre-owned", "preowned", "used", "refurbished")
        )
        is_new = any(x in blob for x in ("brand new", "new", "sealed")) and not is_used

        row = product_row(
            name=name,
            price=price,
            store_name="eBay UK",
            url=href.split("?")[0],
            rating=rating,
            is_used=is_used,
        )
        if row:
            if is_used:
                row["condition"] = "used"
            elif is_new:
                row["condition"] = "new"
            else:
                row["condition"] = "unknown"
            out["results"].append(row)
        if len(out["results"]) >= limit:
            break

    if not out["results"]:
        out["blocked"] = True
    return out


def try_ebay_uk(
    title: str,
    platform: str = "",
    limit: int = 8,
    *,
    min_price: Decimal | None = None,
    max_price: Decimal | None = None,
    condition: str = "",
) -> dict[str, Any]:
    title = (title or "").strip()
    if not title:
        return _empty("")
    lo = str(min_price) if min_price is not None else ""
    hi = str(max_price) if max_price is not None else ""
    cond = (condition or "").strip().lower()
    return cached(
        f"ebay:v4:{title.lower()}:{platform}:{limit}:{lo}:{hi}:{cond}",
        lambda: _try_ebay_uncached(
            title,
            platform=platform,
            limit=limit,
            min_price=min_price,
            max_price=max_price,
            condition=condition,
        ),
        timeout=1800,
    )


def _try_game_uk_uncached(title: str, platform: str = "", limit: int = 8) -> dict[str, Any]:
    q = platform_query(title, platform)
    url = f"https://www.game.co.uk/en/search?q={quote_plus(q)}"
    out: dict[str, Any] = {"results": [], "blocked": False, "search_url": url}
    html, _ = fetch_html(url, timeout=12)
    if not html:
        return _empty(url)
    soup = soup_from(html)

    for script in soup.find_all("script", type="application/ld+json"):
        text = script.string or ""
        for m in re.finditer(
            r'"name"\s*:\s*"([^"]{3,160})".{0,500}?"price"\s*:\s*"?([0-9.]+)',
            text,
            re.DOTALL,
        ):
            try:
                price = Decimal(m.group(2))
            except InvalidOperation:
                continue
            row = product_row(name=m.group(1), price=price, store_name="GAME UK", url=url)
            if row:
                out["results"].append(row)
            if len(out["results"]) >= limit:
                return out

    for card in soup.select(
        "article, .product, [data-product], .product-card, li.product, [class*='ProductCard']"
    )[: limit + 24]:
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


def try_game_uk(title: str, platform: str = "", limit: int = 8) -> dict[str, Any]:
    title = (title or "").strip()
    if not title:
        return _empty("")
    return cached(
        f"gameuk:v4:{title.lower()}:{platform}:{limit}",
        lambda: _try_game_uk_uncached(title, platform=platform, limit=limit),
        timeout=1800,
    )


def _try_argos_uncached(title: str, platform: str = "", limit: int = 8) -> dict[str, Any]:
    q = platform_query(title, platform)
    url = f"https://www.argos.co.uk/search/{quote(q)}/"
    out: dict[str, Any] = {"results": [], "blocked": False, "search_url": url}
    html, _ = fetch_html(url, timeout=12)
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

    for card in soup.select(
        "[data-test='component-product-card'], article, .ProductCard, [class*='ProductCard']"
    )[: limit + 14]:
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


def try_argos(title: str, platform: str = "", limit: int = 8) -> dict[str, Any]:
    title = (title or "").strip()
    if not title:
        return _empty("")
    return cached(
        f"argos:v3:{title.lower()}:{platform}:{limit}",
        lambda: _try_argos_uncached(title, platform=platform, limit=limit),
        timeout=1800,
    )


def _try_currys_uncached(title: str, platform: str = "", limit: int = 8) -> dict[str, Any]:
    q = platform_query(title, platform)
    url = f"https://www.currys.co.uk/search?q={quote_plus(q)}"
    out: dict[str, Any] = {"results": [], "blocked": False, "search_url": url}
    html, _ = fetch_html(url, timeout=12)
    if not html:
        return _empty(url)
    soup = soup_from(html)
    for card in soup.select(
        "[data-component='product-card'], .product, article, [class*='ProductCard']"
    )[: limit + 16]:
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


def try_currys(title: str, platform: str = "", limit: int = 8) -> dict[str, Any]:
    title = (title or "").strip()
    if not title:
        return _empty("")
    return cached(
        f"currys:v3:{title.lower()}:{platform}:{limit}",
        lambda: _try_currys_uncached(title, platform=platform, limit=limit),
        timeout=1800,
    )


def _try_smyths_uncached(title: str, platform: str = "", limit: int = 8) -> dict[str, Any]:
    q = platform_query(title, platform)
    url = f"https://www.smythstoys.com/uk/en-gb/search/?text={quote_plus(q)}"
    out: dict[str, Any] = {"results": [], "blocked": False, "search_url": url}
    html, _ = fetch_html(url, timeout=12)
    if not html:
        return _empty(url)
    soup = soup_from(html)

    for script in soup.find_all("script", type="application/ld+json"):
        text = script.string or ""
        for m in re.finditer(
            r'"name"\s*:\s*"([^"]{3,160})".{0,500}?"price"\s*:\s*"?([0-9.]+)',
            text,
            re.DOTALL,
        ):
            try:
                price = Decimal(m.group(2))
            except InvalidOperation:
                continue
            row = product_row(name=m.group(1), price=price, store_name="Smyths Toys", url=url)
            if row:
                out["results"].append(row)
            if len(out["results"]) >= limit:
                return out

    for card in soup.select(
        ".product-item, .product, article, [class*='product'], [data-product]"
    )[: limit + 20]:
        a = card.find("a", href=True)
        name_el = card.find(["h2", "h3", "a", "span"], class_=re.compile(r"name|title", re.I))
        name = (name_el or a).get_text(" ", strip=True) if (name_el or a) else ""
        if len(name) < 3:
            continue
        price_el = card.find(class_=re.compile(r"price", re.I))
        price = parse_money(price_el.get_text() if price_el else card.get_text(" ", strip=True))
        href = urljoin(url, a["href"]) if a else url
        row = product_row(name=name, price=price, store_name="Smyths Toys", url=href)
        if row:
            out["results"].append(row)
        if len(out["results"]) >= limit:
            break

    if not out["results"]:
        out["blocked"] = True
    return out


def try_smyths(title: str, platform: str = "", limit: int = 8) -> dict[str, Any]:
    title = (title or "").strip()
    if not title:
        return _empty("")
    return cached(
        f"smyths:v2:{title.lower()}:{platform}:{limit}",
        lambda: _try_smyths_uncached(title, platform=platform, limit=limit),
        timeout=1800,
    )


def fetch_uk_physical_bundle(
    title: str,
    platform: str = "",
    limit: int = 8,
    *,
    min_price: Decimal | None = None,
    max_price: Decimal | None = None,
    condition: str = "",
) -> dict[str, Any]:
    """Parallel public scrapes + shared filters (price / condition / platform)."""
    title = (title or "").strip()
    links = uk_search_links(
        title, platform, min_price=min_price, max_price=max_price, condition=condition
    )
    limit = max(4, min(int(limit or 8), 12))
    cond = (condition or "").strip().lower()

    fallback_urls = {link["name"]: link["url"] for link in links}

    def _wrap(fn, fallback_url: str, **extra):
        def run():
            try:
                return fn(title, platform, limit, **extra) if extra else fn(title, platform, limit)
            except TypeError:
                try:
                    return fn(title, platform, limit)
                except Exception:
                    return _empty(fallback_url)
            except Exception:
                return _empty(fallback_url)

        return run

    pool = ThreadPoolExecutor(max_workers=6)
    try:
        f_cex = pool.submit(_wrap(try_cex_search, fallback_urls["CeX"]))
        f_ebay = pool.submit(
            _wrap(
                try_ebay_uk,
                fallback_urls["eBay UK"],
                min_price=min_price,
                max_price=max_price,
                condition=cond,
            )
        )
        f_game = pool.submit(_wrap(try_game_uk, fallback_urls["GAME UK"]))
        f_argos = pool.submit(_wrap(try_argos, fallback_urls["Argos"]))
        f_currys = pool.submit(_wrap(try_currys, fallback_urls["Currys"]))
        f_smyths = pool.submit(_wrap(try_smyths, fallback_urls["Smyths Toys"]))
        completed, _ = wait((f_cex, f_ebay, f_game, f_argos, f_currys, f_smyths), timeout=8)

        def result_if_done(future, fallback_url):
            if future not in completed:
                return _empty(fallback_url)
            try:
                return future.result()
            except Exception:
                return _empty(fallback_url)

        cex = result_if_done(f_cex, fallback_urls["CeX"])
        ebay = result_if_done(f_ebay, fallback_urls["eBay UK"])
        game = result_if_done(f_game, fallback_urls["GAME UK"])
        argos = result_if_done(f_argos, fallback_urls["Argos"])
        currys = result_if_done(f_currys, fallback_urls["Currys"])
        smyths = result_if_done(f_smyths, fallback_urls["Smyths Toys"])
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    # Title match first, then price / condition / platform soft filters
    def finalize(src):
        matched = _keep_matching_rows(src, title)
        return filter_source_dict(
            matched,
            title=title,
            platform=platform,
            min_price=min_price,
            max_price=max_price,
            condition=cond,
        )

    # CeX is always used — if user asked for new only, empty + keep search link
    if cond == "new":
        cex_final = _empty(fallback_urls["CeX"])
        cex_final["search_url"] = cex.get("search_url") or fallback_urls["CeX"]
    else:
        cex_final = finalize(cex)

    return {
        "cex": cex_final,
        "ebay": finalize(ebay),
        "game": finalize(game),
        "argos": finalize(argos),
        "currys": finalize(currys),
        "smyths": finalize(smyths),
        "uk_links": links,
        "filters": {
            "platform": platform,
            "min_price": str(min_price) if min_price is not None else "",
            "max_price": str(max_price) if max_price is not None else "",
            "condition": cond,
        },
    }
