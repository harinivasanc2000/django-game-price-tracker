"""
UK local / marketplace sources — public product search (no login).

  CeX          → boxes JSON API (+ stock / trade-in); BS4 fallback if blocked
  MusicMagpie  → public HTML
  eBay         → public HTML + URL filters
  GAME/Argos/Currys/Smyths → HTML + ld+json

Soft-fail: blocked → empty results + clickable search_url.
Strict title_match filters franchise bleed.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, wait
from decimal import Decimal, InvalidOperation
from typing import Any, Callable
from urllib.parse import quote_plus, quote, urlsplit

from apps.games.cache import cached
from apps.games.clients.cex import search_cex_products
from apps.games.clients.musicmagpie import try_musicmagpie
from apps.games.clients.scrape_filters import filter_source_dict, parse_price_bound
from apps.games.clients.scrape_utils import (
    extract_ld_json_products,
    fetch_html,
    normalise_public_url,
    parse_money,
    parse_rating,
    product_row,
    soup_from,
)
from apps.games.clients.title_match import filter_by_title, titles_match

_HTML_TIMEOUT = 6
_BUNDLE_TIMEOUT = 8
_MAX_STORE_LIMIT = 10


def _clean_query(value: str, *, max_length: int = 160) -> str:
    """Collapse user whitespace and bound URLs/cache keys derived from a title."""
    return re.sub(r"\s+", " ", str(value or "")).strip()[:max_length]


def _safe_limit(value: Any, *, default: int = 8) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(parsed, _MAX_STORE_LIMIT))


def _normalise_condition(value: str) -> str:
    condition = _clean_query(value, max_length=24).lower().replace("_", "-")
    if condition in {"preowned", "pre-owned", "pre owned", "second-hand", "refurbished"}:
        return "used"
    if condition in {"sealed", "brand-new", "brand new"}:
        return "new"
    return condition if condition in {"new", "used"} else ""


def _finite_bound(value: str | Decimal | None) -> Decimal | None:
    bound = parse_price_bound(str(value) if value is not None else None)
    return bound if bound is not None and bound.is_finite() else None


def platform_query(title: str, platform: str = "") -> str:
    t = _clean_query(title)
    p = _clean_query(platform, max_length=32).lower().replace("_", "-")
    hints = {
        "ps3": "PS3",
        "ps4": "PS4",
        "ps5": "PS5",
        "xbox": "Xbox",
        "xbox-one": "Xbox One",
        "xboxone": "Xbox One",
        "xbox-series": "Xbox Series X",
        "xbox-series-x": "Xbox Series X",
        "series-x": "Xbox Series X",
        "switch": "Nintendo Switch",
        "switch-2": "Nintendo Switch 2",
        "switch2": "Nintendo Switch 2",
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
    lo = _finite_bound(min_price)
    hi = _finite_bound(max_price)
    if lo is not None and hi is not None and lo > hi:
        lo, hi = hi, lo
    cond = _normalise_condition(condition)

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
        {"name": "MusicMagpie", "kind": "used-physical", "note": "Used games & media",
         "url": f"https://www.musicmagpie.co.uk/store/search?q={qe}"},
        {"name": "GAME UK", "kind": "retail", "note": "High-street & online",
         "url": f"https://www.game.co.uk/en/search?q={qe}"},
        {"name": "Argos", "kind": "retail", "note": "UK retail",
         "url": f"https://www.argos.co.uk/search/{quote(q, safe='')}/"},
        {"name": "Currys", "kind": "retail", "note": "Electronics & games",
         "url": f"https://www.currys.co.uk/search?q={qe}"},
        {"name": "Smyths Toys", "kind": "retail", "note": "Boxed games / consoles",
         "url": f"https://www.smythstoys.com/uk/en-gb/search/?text={qe}"},
        {"name": "The Game Collection", "kind": "retail", "note": "Games specialist · free UK delivery",
         "url": f"https://www.thegamecollection.net/search?q={qe}&type=product"},
        {"name": "Hit", "kind": "retail", "note": "Games & entertainment · free UK delivery",
         "url": f"https://hit.co.uk/search?q={qe}&type=product"},
        {"name": "ShopTo", "kind": "retail", "note": "Physical games & UK/EU downloads",
         "url": f"https://www.shopto.net/en/search/?input_search={qe}"},
        {"name": "SimplyGames", "kind": "retail", "note": "UK games specialist",
         "url": f"https://www.simplygames.com/search?keywords={qe}"},
        {"name": "Amazon UK", "kind": "marketplace", "note": "New & marketplace",
         "url": f"https://www.amazon.co.uk/s?k={qe}&i=videogames"},
        {"name": "eBay UK", "kind": "marketplace", "note": "Buy It Now · filtered", "url": ebay},
        {"name": "Facebook Marketplace", "kind": "marketplace",
         "note": "Local pickup — open in browser (no auto-scrape)",
         "url": f"https://www.facebook.com/marketplace/search/?query={qe}"},
        {"name": "Gumtree", "kind": "marketplace", "note": "UK classifieds",
         "url": f"https://www.gumtree.com/search?search_category=games&q={qe}"},
        {"name": "Cash Converters", "kind": "used-physical", "note": "Checked second-hand stock from UK shops",
         "url": f"https://www.cashconverters.co.uk/search-results?query={qe}&sort=default"},
        {"name": "Vinted", "kind": "marketplace", "note": "Second-hand marketplace · check seller details",
         "url": f"https://www.vinted.co.uk/catalog?search_text={qe}"},
        {"name": "PriceRunner UK", "kind": "comparison", "note": "Compare UK retailer listings",
         "url": f"https://www.pricerunner.com/results?q={qe}"},
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


def _rows_from_ld(
    soup,
    store_name: str,
    base_url: str,
    limit: int,
    *,
    allowed_hosts: tuple[str, ...],
) -> list[dict]:
    """Convert structured product data while containing outbound URLs."""
    rows: list[dict] = []
    fallback_url = normalise_public_url(base_url, allowed_hosts=allowed_hosts)
    for item in extract_ld_json_products(soup, limit=limit * 3):
        if str(item.get("currency") or "GBP").upper() != "GBP":
            continue
        try:
            price = Decimal(str(item["price"]))
        except (InvalidOperation, KeyError, TypeError):
            continue
        href = normalise_public_url(
            item.get("url"), base_url=base_url, allowed_hosts=allowed_hosts
        )
        used_fallback = not href
        href = href or fallback_url
        row = product_row(name=item.get("name", ""), price=price, store_name=store_name, url=href)
        if row:
            if "in_stock" in item:
                row["in_stock"] = bool(item["in_stock"])
            if used_fallback:
                row["is_search_fallback"] = True
            rows.append(row)
        if len(rows) >= limit * 3:
            break
    return rows


def _rows_from_cards(
    soup,
    *,
    store_name: str,
    base_url: str,
    selectors: str,
    limit: int,
    allowed_hosts: tuple[str, ...],
) -> list[dict]:
    """Parse common retailer cards without treating navigation/year text as price."""
    rows: list[dict] = []
    fallback_url = normalise_public_url(base_url, allowed_hosts=allowed_hosts)
    for card in soup.select(selectors)[: limit + 24]:
        href = ""
        a = None
        # Prefer product-looking anchors and reject an injected cross-domain href.
        for candidate in card.select("a[href]"):
            safe = normalise_public_url(
                candidate.get("href"), base_url=base_url, allowed_hosts=allowed_hosts
            )
            if not safe:
                continue
            a = candidate
            href = safe
            if any(marker in urlsplit(safe).path.lower() for marker in ("/product", "/p/", "-p")):
                break

        name = ""
        for attribute in ("data-product-name", "data-product-title", "data-name", "data-title"):
            if card.get(attribute):
                name = str(card.get(attribute)).strip()
                break
        if not name:
            name_el = card.select_one(
                "[data-product-title], .product-title, .product-name, .card__heading, "
                ".card-product-title, .product-item__title, h2, h3"
            )
            if name_el:
                name = name_el.get_text(" ", strip=True)
        if not name and a:
            name = (a.get("aria-label") or a.get("title") or a.get_text(" ", strip=True)).strip()
        if not name:
            image = card.find("img", alt=True)
            name = image.get("alt", "").strip() if image else ""
        if len(name) < 3:
            continue

        price_el = None
        # Selector order matters: an old/RRP node often appears before the sale
        # price in the DOM, so query preferred live-price shapes one at a time.
        for price_selector in (
            "[data-product-price]",
            ".price-item--sale",
            ".price__current",
            ".current-price",
            ".sales-price",
            "[itemprop='price']",
            "[class*='price']",
        ):
            price_el = card.select_one(price_selector)
            if price_el is not None:
                break
        if price_el and price_el.get("content"):
            price = parse_money(price_el.get("content"))
        else:
            price = parse_money(
                price_el.get_text(" ", strip=True) if price_el else card.get_text(" ", strip=True),
                require_currency=price_el is None,
            )
        used_fallback = not href
        href = href or fallback_url
        row = product_row(name=name, price=price, store_name=store_name, url=href)
        if row:
            blob = card.get_text(" ", strip=True).lower()
            if any(marker in blob for marker in ("out of stock", "sold out", "unavailable")):
                row["in_stock"] = False
            elif any(marker in blob for marker in ("in stock", "add to cart", "buy now")):
                row["in_stock"] = True
            if used_fallback:
                row["is_search_fallback"] = True
            rows.append(row)
        if len(rows) >= limit * 3:
            break
    return rows


def _dedupe_rows(rows: list[dict]) -> list[dict]:
    """Collapse repeated mobile/desktop cards, retaining the strongest offer."""
    chosen: dict[tuple[str, str, str], dict] = {}

    def quality(row: dict) -> tuple:
        try:
            price = float(row.get("price"))
        except (TypeError, ValueError):
            price = 999999.0
        return (
            1 if row.get("in_stock") is False else 0,
            1 if row.get("is_search_fallback") or not row.get("url") else 0,
            -float(row.get("match_score") or 0),
            price,
        )

    for row in rows:
        name = re.sub(r"\s+", " ", str(row.get("name") or "")).strip().casefold()
        store = re.sub(r"\s+", " ", str(row.get("store_name") or "")).strip().casefold()
        condition = str(row.get("condition") or "").casefold()
        if not name:
            continue
        key = (store, name, condition)
        if key not in chosen or quality(row) < quality(chosen[key]):
            chosen[key] = row
    return list(chosen.values())


def _finalize_store(rows: list, title: str, limit: int, search_url: str) -> dict[str, Any]:
    limit = _safe_limit(limit)
    matched = _dedupe_rows(filter_by_title(rows, title, min_score=0.67))
    matched.sort(
        key=lambda row: (
            1 if row.get("in_stock") is False else 0,
            -float(row.get("match_score") or 0),
            1 if row.get("is_search_fallback") or not row.get("url") else 0,
            float(row.get("price") or 999999),
        )
    )
    matched = matched[:limit]
    return {
        "results": matched,
        "blocked": len(matched) == 0,
        "search_url": search_url,
    }


def merge_best_local(sources: dict[str, dict], *, limit: int = 10) -> list[dict]:
    merged: list[dict] = []
    for key, src in sources.items():
        for row in src.get("results") or []:
            # Sold-out rows remain visible in their retailer section, but a
            # non-purchasable listing must never be advertised as "cheapest".
            if row.get("in_stock") is False:
                continue
            item = dict(row)
            item.setdefault("store_name", key)
            merged.append(item)
    merged = _dedupe_rows(merged)
    merged.sort(
        key=lambda row: (
            1 if row.get("in_stock") is False else 0,
            1 if row.get("is_search_fallback") or not row.get("url") else 0,
            float(row["price"]) if row.get("price") is not None else 999999.0,
            -float(row.get("match_score") or 0),
            str(row.get("store_name") or "").casefold(),
        )
    )
    return merged[:_safe_limit(limit, default=10)]


def try_cex_search(title: str, platform: str = "", limit: int = 8) -> dict[str, Any]:
    title = _clean_query(title)
    if not title:
        return _empty("")
    limit = _safe_limit(limit)
    return cached(
        f"cex:v8:{title.lower()}:{platform}:{limit}",
        lambda: search_cex_products(title, platform=platform, limit=limit),
        timeout=1800,
    )


def _ebay_search_url(
    title: str,
    platform: str = "",
    *,
    min_price: Decimal | None = None,
    max_price: Decimal | None = None,
    condition: str = "",
) -> str:
    min_price = _finite_bound(min_price)
    max_price = _finite_bound(max_price)
    if min_price is not None and max_price is not None and min_price > max_price:
        min_price, max_price = max_price, min_price
    q = platform_query(title, platform)
    url = (
        f"https://www.ebay.co.uk/sch/i.html?_nkw={quote_plus(q)}"
        f"&_sacat=139973&LH_BIN=1&_sop=15"
    )
    if min_price is not None:
        url += f"&_udlo={min_price}"
    if max_price is not None:
        url += f"&_udhi={max_price}"
    cond = _normalise_condition(condition)
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
    limit = _safe_limit(limit)
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
        href = normalise_public_url(
            link_el.get("href") if link_el else "",
            base_url=url,
            allowed_hosts=("ebay.co.uk",),
        )
        used_fallback = not href
        href = href or url
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
            url=href,
            rating=rating,
            is_used=is_used,
        )
        if row:
            row["condition"] = "used" if is_used else ("new" if "new" in blob else "unknown")
            if used_fallback:
                row["is_search_fallback"] = True
            rows.append(row)
        if len(rows) >= limit * 2:
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
    title = _clean_query(title)
    if not title:
        return _empty("")
    limit = _safe_limit(limit)
    lo = str(min_price) if min_price is not None else ""
    hi = str(max_price) if max_price is not None else ""
    cond = _normalise_condition(condition)
    return cached(
        f"ebay:v8:{title.lower()}:{platform}:{limit}:{lo}:{hi}:{cond}",
        lambda: _try_ebay_uncached(
            title, platform=platform, limit=limit,
            min_price=min_price, max_price=max_price, condition=cond,
        ),
        timeout=1800,
    )


def _try_game_uk_uncached(title: str, platform: str = "", limit: int = 8) -> dict[str, Any]:
    limit = _safe_limit(limit)
    q = platform_query(title, platform)
    url = f"https://www.game.co.uk/en/search?q={quote_plus(q)}"
    html, _ = fetch_html(url, timeout=_HTML_TIMEOUT, referer="https://www.game.co.uk/")
    if not html:
        return _empty(url)
    soup = soup_from(html)
    rows = _rows_from_ld(soup, "GAME UK", url, limit, allowed_hosts=("game.co.uk",))
    if len(rows) < limit:
        rows.extend(
            _rows_from_cards(
                soup, store_name="GAME UK", base_url=url,
                selectors="article, .product-card, [data-product], li.product, [class*='ProductCard']",
                limit=limit,
                allowed_hosts=("game.co.uk",),
            )
        )
    return _finalize_store(rows, title, limit, url)


def try_game_uk(title: str, platform: str = "", limit: int = 8) -> dict[str, Any]:
    title = _clean_query(title)
    if not title:
        return _empty("")
    limit = _safe_limit(limit)
    return cached(
        f"gameuk:v8:{title.lower()}:{platform}:{limit}",
        lambda: _try_game_uk_uncached(title, platform=platform, limit=limit),
        timeout=1800,
    )


def _try_argos_uncached(title: str, platform: str = "", limit: int = 8) -> dict[str, Any]:
    limit = _safe_limit(limit)
    q = platform_query(title, platform)
    url = f"https://www.argos.co.uk/search/{quote(q, safe='')}/"
    html, _ = fetch_html(url, timeout=_HTML_TIMEOUT, referer="https://www.argos.co.uk/")
    if not html:
        return _empty(url)
    soup = soup_from(html)
    rows = _rows_from_ld(soup, "Argos", url, limit, allowed_hosts=("argos.co.uk",))
    if len(rows) < limit:
        for script in soup.find_all("script"):
            text = script.string or ""
            if '"name"' not in text or '"price"' not in text:
                continue
            for m in re.finditer(
                r'"name"\s*:\s*"([^"]{5,120})".{0,280}?"price"\s*:\s*([0-9]+(?:\.[0-9]+)?)',
                text, re.DOTALL,
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
                soup, store_name="Argos", base_url=url,
                selectors="[data-test='component-product-card'], article, [class*='ProductCard']",
                limit=limit,
                allowed_hosts=("argos.co.uk",),
            )
        )
    return _finalize_store(rows, title, limit, url)


def try_argos(title: str, platform: str = "", limit: int = 8) -> dict[str, Any]:
    title = _clean_query(title)
    if not title:
        return _empty("")
    limit = _safe_limit(limit)
    return cached(
        f"argos:v7:{title.lower()}:{platform}:{limit}",
        lambda: _try_argos_uncached(title, platform=platform, limit=limit),
        timeout=1800,
    )


def _try_currys_uncached(title: str, platform: str = "", limit: int = 8) -> dict[str, Any]:
    limit = _safe_limit(limit)
    q = platform_query(title, platform)
    url = f"https://www.currys.co.uk/search?q={quote_plus(q)}"
    html, _ = fetch_html(url, timeout=_HTML_TIMEOUT, referer="https://www.currys.co.uk/")
    if not html:
        return _empty(url)
    soup = soup_from(html)
    rows = _rows_from_ld(soup, "Currys", url, limit, allowed_hosts=("currys.co.uk",))
    if len(rows) < limit:
        rows.extend(
            _rows_from_cards(
                soup, store_name="Currys", base_url=url,
                selectors="[data-component='product-card'], .product, article, [class*='ProductCard']",
                limit=limit,
                allowed_hosts=("currys.co.uk",),
            )
        )
    return _finalize_store(rows, title, limit, url)


def try_currys(title: str, platform: str = "", limit: int = 8) -> dict[str, Any]:
    title = _clean_query(title)
    if not title:
        return _empty("")
    limit = _safe_limit(limit)
    return cached(
        f"currys:v7:{title.lower()}:{platform}:{limit}",
        lambda: _try_currys_uncached(title, platform=platform, limit=limit),
        timeout=1800,
    )


def _try_smyths_uncached(title: str, platform: str = "", limit: int = 8) -> dict[str, Any]:
    limit = _safe_limit(limit)
    q = platform_query(title, platform)
    url = f"https://www.smythstoys.com/uk/en-gb/search/?text={quote_plus(q)}"
    html, _ = fetch_html(
        url, timeout=_HTML_TIMEOUT, referer="https://www.smythstoys.com/uk/en-gb/"
    )
    if not html:
        return _empty(url)
    soup = soup_from(html)
    rows = _rows_from_ld(
        soup, "Smyths Toys", url, limit, allowed_hosts=("smythstoys.com",)
    )
    if len(rows) < limit:
        rows.extend(
            _rows_from_cards(
                soup, store_name="Smyths Toys", base_url=url,
                selectors=".product-item, .product, article, [class*='product'], [data-product]",
                limit=limit,
                allowed_hosts=("smythstoys.com",),
            )
        )
    return _finalize_store(rows, title, limit, url)


def try_smyths(title: str, platform: str = "", limit: int = 8) -> dict[str, Any]:
    title = _clean_query(title)
    if not title:
        return _empty("")
    limit = _safe_limit(limit)
    return cached(
        f"smyths:v6:{title.lower()}:{platform}:{limit}",
        lambda: _try_smyths_uncached(title, platform=platform, limit=limit),
        timeout=1800,
    )


_SPECIALIST_STORES: dict[str, dict[str, Any]] = {
    "tgc": {
        "name": "The Game Collection",
        "base": "https://www.thegamecollection.net/",
        "url": "https://www.thegamecollection.net/search?q={query}&type=product",
        "hosts": ("thegamecollection.net",),
        "selectors": "product-card, .card, .product-card, li.grid__item, [data-product-id]",
    },
    "hit": {
        "name": "Hit",
        "base": "https://hit.co.uk/",
        "url": "https://hit.co.uk/search?q={query}&type=product",
        "hosts": ("hit.co.uk",),
        "selectors": "product-card, .card-product, .product-card, li.grid__item, [data-product-id]",
    },
    "shopto": {
        "name": "ShopTo",
        "base": "https://www.shopto.net/en/",
        "url": "https://www.shopto.net/en/search/?input_search={query}",
        "hosts": ("shopto.net",),
        "selectors": ".itemlist_item, .product, article, [data-item-id], [class*='product']",
    },
    "simplygames": {
        "name": "SimplyGames",
        "base": "https://www.simplygames.com/",
        "url": "https://www.simplygames.com/search?keywords={query}",
        "hosts": ("simplygames.com",),
        "selectors": ".product, .product-item, article, li.product, [data-product-id]",
    },
}


def _try_specialist_uncached(
    store_key: str, title: str, platform: str = "", limit: int = 8
) -> dict[str, Any]:
    """BS4 a UK specialist using a small declarative store configuration."""
    spec = _SPECIALIST_STORES[store_key]
    limit = _safe_limit(limit)
    query = quote_plus(platform_query(title, platform))
    url = str(spec["url"]).format(query=query)
    html, _ = fetch_html(url, timeout=_HTML_TIMEOUT, referer=spec["base"])
    if not html:
        return _empty(url)
    soup = soup_from(html)
    rows = _rows_from_ld(
        soup,
        spec["name"],
        url,
        limit,
        allowed_hosts=spec["hosts"],
    )
    if len(rows) < limit:
        rows.extend(
            _rows_from_cards(
                soup,
                store_name=spec["name"],
                base_url=url,
                selectors=spec["selectors"],
                limit=limit,
                allowed_hosts=spec["hosts"],
            )
        )
    return _finalize_store(rows, title, limit, url)


def _try_specialist(
    store_key: str, title: str, platform: str = "", limit: int = 8
) -> dict[str, Any]:
    title = _clean_query(title)
    if not title:
        return _empty("")
    limit = _safe_limit(limit)
    return cached(
        f"uk-specialist:v1:{store_key}:{title.lower()}:{platform}:{limit}",
        lambda: _try_specialist_uncached(store_key, title, platform, limit),
        timeout=1800,
    )


def try_the_game_collection(title: str, platform: str = "", limit: int = 8) -> dict[str, Any]:
    return _try_specialist("tgc", title, platform, limit)


def try_hit(title: str, platform: str = "", limit: int = 8) -> dict[str, Any]:
    return _try_specialist("hit", title, platform, limit)


def try_shopto(title: str, platform: str = "", limit: int = 8) -> dict[str, Any]:
    return _try_specialist("shopto", title, platform, limit)


def try_simplygames(title: str, platform: str = "", limit: int = 8) -> dict[str, Any]:
    return _try_specialist("simplygames", title, platform, limit)


def fetch_uk_physical_bundle(
    title: str,
    platform: str = "",
    limit: int = 8,
    *,
    min_price: Decimal | None = None,
    max_price: Decimal | None = None,
    condition: str = "",
) -> dict[str, Any]:
    title = _clean_query(title)
    min_price = _finite_bound(min_price)
    max_price = _finite_bound(max_price)
    if min_price is not None and max_price is not None and min_price > max_price:
        min_price, max_price = max_price, min_price
    links = uk_search_links(
        title, platform, min_price=min_price, max_price=max_price, condition=condition
    )
    limit = max(4, _safe_limit(limit))
    cond = _normalise_condition(condition)
    fallback = {link["name"]: link["url"] for link in links}

    def safe(name: str, fn: Callable[[], dict]) -> Callable[[], dict]:
        def run():
            try:
                return fn()
            except Exception:
                return _empty(fallback.get(name, ""))

        return run

    pool = ThreadPoolExecutor(max_workers=11)
    try:
        f_cex = pool.submit(safe("CeX", lambda: try_cex_search(title, platform, limit)))
        f_mm = pool.submit(
            safe("MusicMagpie", lambda: try_musicmagpie(title, platform, limit))
        )
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
        f_tgc = pool.submit(
            safe(
                "The Game Collection",
                lambda: try_the_game_collection(title, platform, limit),
            )
        )
        f_hit = pool.submit(safe("Hit", lambda: try_hit(title, platform, limit)))
        f_shopto = pool.submit(safe("ShopTo", lambda: try_shopto(title, platform, limit)))
        f_simply = pool.submit(
            safe("SimplyGames", lambda: try_simplygames(title, platform, limit))
        )

        done, _ = wait(
            (
                f_cex, f_mm, f_ebay, f_game, f_argos, f_currys, f_smyths,
                f_tgc, f_hit, f_shopto, f_simply,
            ),
            timeout=_BUNDLE_TIMEOUT,
        )

        def take(fut, name):
            if fut not in done:
                return _empty(fallback.get(name, ""))
            try:
                return fut.result() or _empty(fallback.get(name, ""))
            except Exception:
                return _empty(fallback.get(name, ""))

        cex = take(f_cex, "CeX")
        mm = take(f_mm, "MusicMagpie")
        ebay = take(f_ebay, "eBay UK")
        game = take(f_game, "GAME UK")
        argos = take(f_argos, "Argos")
        currys = take(f_currys, "Currys")
        smyths = take(f_smyths, "Smyths Toys")
        tgc = take(f_tgc, "The Game Collection")
        hit = take(f_hit, "Hit")
        shopto = take(f_shopto, "ShopTo")
        simplygames = take(f_simply, "SimplyGames")
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    def finalize(src):
        matched = _keep_matching_rows(src, title)
        filtered = filter_source_dict(
            matched,
            title=title,
            platform=platform,
            min_price=min_price,
            max_price=max_price,
            condition=cond,
        )
        filtered["results"].sort(
            key=lambda row: (
                1 if row.get("in_stock") is False else 0,
                -float(row.get("match_score") or 0),
                float(row.get("price") or 999999),
            )
        )
        return filtered

    if cond == "new":
        cex_final = _empty(fallback["CeX"])
        cex_final["search_url"] = cex.get("search_url") or fallback["CeX"]
        mm_final = _empty(fallback["MusicMagpie"])
        mm_final["search_url"] = mm.get("search_url") or fallback["MusicMagpie"]
    else:
        cex_final = finalize(cex)
        mm_final = finalize(mm)

    sources = {
        "cex": cex_final,
        "musicmagpie": mm_final,
        "ebay": finalize(ebay),
        "game": finalize(game),
        "argos": finalize(argos),
        "currys": finalize(currys),
        "smyths": finalize(smyths),
        "the_game_collection": finalize(tgc),
        "hit": finalize(hit),
        "shopto": finalize(shopto),
        "simplygames": finalize(simplygames),
    }
    best_local = merge_best_local(sources, limit=10)
    stores_ok = sum(1 for s in sources.values() if s.get("results"))

    return {
        **sources,
        "uk_links": links,
        "best_local": best_local,
        "stores_ok": stores_ok,
        "stores_total": len(sources),
        "filters": {
            "platform": platform,
            "min_price": str(min_price) if min_price is not None else "",
            "max_price": str(max_price) if max_price is not None else "",
            "condition": cond,
        },
    }
