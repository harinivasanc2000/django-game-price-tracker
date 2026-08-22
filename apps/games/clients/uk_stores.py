"""
UK local / marketplace sources — public product search (no login).

  CeX     → official boxes JSON API (wss2.cex.uk.webuy.io) — fastest / most reliable
  eBay    → public HTML + URL filters (BIN, price, condition)
  GAME / Argos / Currys / Smyths → public HTML + ld+json when present

Soft-fail everywhere: blocked → empty results + clickable search_url.
Strict title_match so franchise bleed (LEGO etc.) is filtered out.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, wait
from decimal import Decimal, InvalidOperation
from typing import Any, Callable
from urllib.parse import quote_plus, quote, urljoin

from apps.games.cache import cached
from apps.games.clients.cex import search_cex_products
from apps.games.clients.scrape_filters import filter_source_dict, parse_price_bound
from apps.games.clients.scrape_utils import (
    extract_ld_json_products,
    fetch_html,
    parse_money,
    parse_rating,
    product_row,
    soup_from,
)
from apps.games.clients.title_match import filter_by_title, titles_match

# Per-store HTML budget (CeX uses JSON and is separate)
_HTML_TIMEOUT = 7
_BUNDLE_TIMEOUT = 8


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
        {"name": "CeX", "kind": "used-physical", "note": "Buy / sell used discs",
         "url": f"https://uk.webuy.com/search?stext={qe}"},
        {"name": "GAME UK", "kind": "retail", "note": "High-street & online",
         "url": f"https://www.game.co.uk/en/search?q={qe}"},
        {"name": "Argos", "kind": "retail", "note": "UK retail",
         "url": f"https://www.argos.co.uk/search/{quote(q)}/"},
        {"name": "Currys", "kind": "retail", "note": "Electronics & games",
         "url": f"https://www.currys.co.uk/search?q={qe}"},
        {"name": "Smyths Toys", "kind": "retail", "note": "Boxed games / consoles",
         "url": f"https://www.smythstoys.com/uk/en-gb/search/?text={qe}"},
        {"name": "Amazon UK", "kind": "marketplace", "note": "New & marketplace",
         "url": f"https://www.amazon.co.uk/s?k={qe}&i=videogames"},
        {"name": "eBay UK", "kind": "marketplace", "note": "Buy It Now · filtered", "url": ebay},
        {"name": "Facebook Marketplace", "kind": "marketplace",
         "note": "Local pickup — open in browser (no auto-scrape)",
         "url": f"https://www.facebook.com/marketplace/search/?query={qe}"},
        {"name": "Gumtree", "kind": "marketplace", "note": "UK classifieds",
         "url": f"https://www.gumtree.com/search?search_category=games&q={qe}"},
    ]


def _empty(url: str) -> dict[str, Any]:
    return {"results": [], "blocked": True, "search_url": url}


def _title_matches(name: str, title: str) -> bool:
    return titles_match(name, title, min_score=0.67)


def _keep_matching_rows(source: dict[str, Any], title: str) -> dict[str, Any]:
    source = dict(source or {})
    source["results"] = filter_by_title(source.get("results") or [], title, min_score=0.67)
    if not source["results"]:
        source["blocked"] = True
    return source


def _rows_from_ld(soup, store_name: str, base_url: str, limit: int) -> list[dict]:
    rows = []
    for item in extract_ld_json_products(soup, limit=limit * 2):
        try:
            price = Decimal(str(item["price"]))
        except (InvalidOperation, KeyError, TypeError):
            continue
        href = item.get("url") or base_url
        if href and not href.startswith("http"):
            href = urljoin(base_url, href)
        row = product_row(name=item.get("name", ""), price=price, store_name=store_name, url=href)
        if row:
            rows.append(row)
        if len(rows) >= limit * 2:
            break
    return rows


def _rows_from_cards(
    soup,
    *,
    store_name: str,
    base_url: str,
    selectors: str,
    limit: int,
) -> list[dict]:
    rows = []
    for card in soup.select(selectors)[: limit + 20]:
        a = card.find("a", href=True)
        name_el = card.find(["h2", "h3", "span", "a"], class_=re.compile(r"name|title|product", re.I))
        if not name_el:
            name_el = a
        name = name_el.get_text(" ", strip=True) if name_el else ""
        if len(name) < 3:
            continue
        price_el = card.find(class_=re.compile(r"price", re.I))
        price = parse_money(price_el.get_text() if price_el else card.get_text(" ", strip=True))
        href = urljoin(base_url, a["href"]) if a else base_url
        row = product_row(name=name, price=price, store_name=store_name, url=href)
        if row:
            rows.append(row)
        if len(rows) >= limit * 2:
            break
    return rows


def _finalize_store(rows: list, title: str, limit: int, search_url: str) -> dict[str, Any]:
    matched = filter_by_title(rows, title, min_score=0.67)[:limit]
    return {
        "results": matched,
        "blocked": len(matched) == 0,
        "search_url": search_url,
    }


# ── CeX (JSON API) ──────────────────────────────────────────────

def try_cex_search(title: str, platform: str = "", limit: int = 8) -> dict[str, Any]:
    title = (title or "").strip()
    if not title:
        return _empty("")
    return cached(
        f"cex:v6:{title.lower()}:{platform}:{limit}",
        lambda: search_cex_products(title, platform=platform, limit=limit),
        timeout=1800,
    )


# ── eBay ────────────────────────────────────────────────────────

def _ebay_search_url(
    title: str,
    platform: str = "",
    *,
    min_price: Decimal | None = None,
    max_price: Decimal | None = None,
    condition: str = "",
) -> str:
    q = platform_query(title, platform)
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
    html, _ = fetch_html(url, timeout=_HTML_TIMEOUT, referer="https://www.ebay.co.uk/")
    if not html:
        return _empty(url)

    soup = soup_from(html)
    rows = []
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
        rating_el = item.select_one(".x-star-rating, .s-item__seller-info-text")
        if rating_el:
            rating = parse_rating(rating_el.get_text(" ", strip=True))
        subtitle = ""
        sub_el = item.select_one(".SECONDARY_INFO, .s-item__subtitle")
        if sub_el:
            subtitle = sub_el.get_text(" ", strip=True)
        blob = f"{name} {subtitle}".lower()
        is_used = any(x in blob for x in ("pre-owned", "preowned", "used", "refurbished"))
        row = product_row(
            name=name,
            price=price,
            store_name="eBay UK",
            url=href.split("?")[0],
            rating=rating,
            is_used=is_used,
        )
        if row:
            row["condition"] = "used" if is_used else ("new" if "new" in blob else "unknown")
            rows.append(row)
        if len(rows) >= limit * 3:
            break
    return _finalize_store(rows, title, limit, url)


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
        f"ebay:v6:{title.lower()}:{platform}:{limit}:{lo}:{hi}:{cond}",
        lambda: _try_ebay_uncached(
            title, platform=platform, limit=limit,
            min_price=min_price, max_price=max_price, condition=condition,
        ),
        timeout=1800,
    )


# ── GAME UK ─────────────────────────────────────────────────────

def _try_game_uk_uncached(title: str, platform: str = "", limit: int = 8) -> dict[str, Any]:
    q = platform_query(title, platform)
    url = f"https://www.game.co.uk/en/search?q={quote_plus(q)}"
    html, _ = fetch_html(url, timeout=_HTML_TIMEOUT, referer="https://www.game.co.uk/")
    if not html:
        return _empty(url)
    soup = soup_from(html)
    rows = _rows_from_ld(soup, "GAME UK", url, limit)
    if len(rows) < limit:
        rows.extend(
            _rows_from_cards(
                soup,
                store_name="GAME UK",
                base_url=url,
                selectors="article, .product-card, [data-product], li.product, [class*='ProductCard']",
                limit=limit,
            )
        )
    return _finalize_store(rows, title, limit, url)


def try_game_uk(title: str, platform: str = "", limit: int = 8) -> dict[str, Any]:
    title = (title or "").strip()
    if not title:
        return _empty("")
    return cached(
        f"gameuk:v6:{title.lower()}:{platform}:{limit}",
        lambda: _try_game_uk_uncached(title, platform=platform, limit=limit),
        timeout=1800,
    )


# ── Argos ───────────────────────────────────────────────────────

def _try_argos_uncached(title: str, platform: str = "", limit: int = 8) -> dict[str, Any]:
    q = platform_query(title, platform)
    url = f"https://www.argos.co.uk/search/{quote(q)}/"
    html, _ = fetch_html(url, timeout=_HTML_TIMEOUT, referer="https://www.argos.co.uk/")
    if not html:
        return _empty(url)
    soup = soup_from(html)
    rows = _rows_from_ld(soup, "Argos", url, limit)
    if len(rows) < limit:
        # Argos often embeds product JSON in scripts
        for script in soup.find_all("script"):
            text = script.string or ""
            if '"name"' not in text or '"price"' not in text:
                continue
            for m in re.finditer(
                r'"name"\s*:\s*"([^"]{5,120})".{0,280}?"price"\s*:\s*([0-9]+(?:\.[0-9]+)?)',
                text,
                re.DOTALL,
            ):
                name = m.group(1)
                if "argos" in name.lower():
                    continue
                try:
                    price = Decimal(m.group(2))
                except InvalidOperation:
                    continue
                row = product_row(name=name, price=price, store_name="Argos", url=url)
                if row:
                    rows.append(row)
                if len(rows) >= limit * 2:
                    break
            if len(rows) >= limit * 2:
                break
    if len(rows) < limit:
        rows.extend(
            _rows_from_cards(
                soup,
                store_name="Argos",
                base_url=url,
                selectors="[data-test='component-product-card'], article, [class*='ProductCard']",
                limit=limit,
            )
        )
    return _finalize_store(rows, title, limit, url)


def try_argos(title: str, platform: str = "", limit: int = 8) -> dict[str, Any]:
    title = (title or "").strip()
    if not title:
        return _empty("")
    return cached(
        f"argos:v5:{title.lower()}:{platform}:{limit}",
        lambda: _try_argos_uncached(title, platform=platform, limit=limit),
        timeout=1800,
    )


# ── Currys ──────────────────────────────────────────────────────

def _try_currys_uncached(title: str, platform: str = "", limit: int = 8) -> dict[str, Any]:
    q = platform_query(title, platform)
    url = f"https://www.currys.co.uk/search?q={quote_plus(q)}"
    html, _ = fetch_html(url, timeout=_HTML_TIMEOUT, referer="https://www.currys.co.uk/")
    if not html:
        return _empty(url)
    soup = soup_from(html)
    rows = _rows_from_ld(soup, "Currys", url, limit)
    if len(rows) < limit:
        rows.extend(
            _rows_from_cards(
                soup,
                store_name="Currys",
                base_url=url,
                selectors="[data-component='product-card'], .product, article, [class*='ProductCard']",
                limit=limit,
            )
        )
    return _finalize_store(rows, title, limit, url)


def try_currys(title: str, platform: str = "", limit: int = 8) -> dict[str, Any]:
    title = (title or "").strip()
    if not title:
        return _empty("")
    return cached(
        f"currys:v5:{title.lower()}:{platform}:{limit}",
        lambda: _try_currys_uncached(title, platform=platform, limit=limit),
        timeout=1800,
    )


# ── Smyths ──────────────────────────────────────────────────────

def _try_smyths_uncached(title: str, platform: str = "", limit: int = 8) -> dict[str, Any]:
    q = platform_query(title, platform)
    url = f"https://www.smythstoys.com/uk/en-gb/search/?text={quote_plus(q)}"
    html, _ = fetch_html(
        url, timeout=_HTML_TIMEOUT, referer="https://www.smythstoys.com/uk/en-gb/"
    )
    if not html:
        return _empty(url)
    soup = soup_from(html)
    rows = _rows_from_ld(soup, "Smyths Toys", url, limit)
    if len(rows) < limit:
        rows.extend(
            _rows_from_cards(
                soup,
                store_name="Smyths Toys",
                base_url=url,
                selectors=".product-item, .product, article, [class*='product'], [data-product]",
                limit=limit,
            )
        )
    return _finalize_store(rows, title, limit, url)


def try_smyths(title: str, platform: str = "", limit: int = 8) -> dict[str, Any]:
    title = (title or "").strip()
    if not title:
        return _empty("")
    return cached(
        f"smyths:v4:{title.lower()}:{platform}:{limit}",
        lambda: _try_smyths_uncached(title, platform=platform, limit=limit),
        timeout=1800,
    )


# ── Parallel bundle ─────────────────────────────────────────────

def fetch_uk_physical_bundle(
    title: str,
    platform: str = "",
    limit: int = 8,
    *,
    min_price: Decimal | None = None,
    max_price: Decimal | None = None,
    condition: str = "",
) -> dict[str, Any]:
    """
    Parallel public scrapes.
    CeX uses JSON API (usually <1s); HTML stores share an 8s hard deadline.
    """
    title = (title or "").strip()
    links = uk_search_links(
        title, platform, min_price=min_price, max_price=max_price, condition=condition
    )
    limit = max(4, min(int(limit or 8), 12))
    cond = (condition or "").strip().lower()
    fallback = {link["name"]: link["url"] for link in links}

    def safe(name: str, fn: Callable[[], dict]) -> Callable[[], dict]:
        def run():
            try:
                return fn()
            except Exception:
                return _empty(fallback.get(name, ""))

        return run

    pool = ThreadPoolExecutor(max_workers=6)
    try:
        f_cex = pool.submit(safe("CeX", lambda: try_cex_search(title, platform, limit)))
        f_ebay = pool.submit(
            safe(
                "eBay UK",
                lambda: try_ebay_uk(
                    title, platform, limit,
                    min_price=min_price, max_price=max_price, condition=cond,
                ),
            )
        )
        f_game = pool.submit(safe("GAME UK", lambda: try_game_uk(title, platform, limit)))
        f_argos = pool.submit(safe("Argos", lambda: try_argos(title, platform, limit)))
        f_currys = pool.submit(safe("Currys", lambda: try_currys(title, platform, limit)))
        f_smyths = pool.submit(safe("Smyths Toys", lambda: try_smyths(title, platform, limit)))

        done, _ = wait(
            (f_cex, f_ebay, f_game, f_argos, f_currys, f_smyths),
            timeout=_BUNDLE_TIMEOUT,
        )

        def take(fut, name):
            if fut not in done:
                return _empty(fallback[name])
            try:
                return fut.result() or _empty(fallback[name])
            except Exception:
                return _empty(fallback[name])

        cex = take(f_cex, "CeX")
        ebay = take(f_ebay, "eBay UK")
        game = take(f_game, "GAME UK")
        argos = take(f_argos, "Argos")
        currys = take(f_currys, "Currys")
        smyths = take(f_smyths, "Smyths Toys")
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

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

    if cond == "new":
        cex_final = _empty(fallback["CeX"])
        cex_final["search_url"] = cex.get("search_url") or fallback["CeX"]
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
