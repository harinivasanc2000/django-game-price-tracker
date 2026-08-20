"""
Additional digital stores — public *search* HTML only (BeautifulSoup).

Collected fields only:
  name, price, currency, product url, store_name, optional public rating
Never: personal seller PII.

Keyshops (CDKeys, Eneba, etc.) may be blocked and are labelled third-party.
Always returns search_url fallback.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.parse import quote_plus, urljoin

from apps.games.cache import cached
from apps.games.clients.scrape_utils import (
    fetch_html,
    parse_money,
    product_row,
    soup_from,
)


def _empty(url: str) -> dict[str, Any]:
    return {"results": [], "blocked": True, "search_url": url}


def _safe(fn, *a, **k):
    try:
        return fn(*a, **k)
    except Exception:
        return _empty(k.get("url") or "")


def digital_search_links(title: str) -> list[dict[str, str]]:
    q = quote_plus((title or "").strip())
    return [
        {"name": "Humble Store", "kind": "official", "url": f"https://www.humblebundle.com/store/search?search={q}"},
        {"name": "Fanatical", "kind": "retail", "url": f"https://www.fanatical.com/en/search?search={q}"},
        {"name": "Green Man Gaming", "kind": "retail", "url": f"https://www.greenmangaming.com/search?query={q}"},
        {"name": "GOG", "kind": "official", "url": f"https://www.gog.com/en/games?query={q}"},
        {"name": "Epic Games Store", "kind": "official", "url": f"https://store.epicgames.com/en-US/browse?q={q}&sortBy=relevancy"},
        {"name": "CDKeys", "kind": "third-party", "url": f"https://www.cdkeys.com/?q={q}"},
        {"name": "Eneba", "kind": "third-party", "url": f"https://www.eneba.com/store?text={q}"},
        {"name": "AllKeyShop", "kind": "meta", "url": f"https://www.allkeyshop.com/blog/catalogue/search-{q}/"},
        {"name": "GG.deals", "kind": "meta", "url": f"https://gg.deals/games/?title={q}"},
        {"name": "IsThereAnyDeal", "kind": "meta", "url": f"https://isthereanydeal.com/search/?q={q}"},
    ]


def _try_humble(title: str, limit: int = 5) -> dict[str, Any]:
    url = f"https://www.humblebundle.com/store/search?search={quote_plus(title)}"
    out: dict[str, Any] = {"results": [], "blocked": False, "search_url": url}
    html, _ = fetch_html(url)
    if not html:
        return _empty(url)
    soup = soup_from(html)
    for card in soup.select(".entity-title, .store-entity, [class*='entity']")[: limit + 15]:
        a = card if card.name == "a" else card.find("a", href=True)
        if not a:
            parent = card.find_parent(["div", "li", "article"])
            a = parent.find("a", href=True) if parent else None
        name = (a or card).get_text(" ", strip=True)
        if len(name) < 2:
            continue
        href = urljoin(url, a["href"]) if a and a.get("href") else url
        price = None
        root = card.find_parent(["div", "li", "article"]) or card
        price_el = root.find(class_=lambda c: c and "price" in str(c).lower()) if hasattr(root, "find") else None
        if price_el:
            price = parse_money(price_el.get_text())
        if price is None:
            price = parse_money(root.get_text(" ", strip=True))
        row = product_row(name=name, price=price, currency="GBP", url=href, store_name="Humble Store")
        if row:
            out["results"].append(row)
        if len(out["results"]) >= limit:
            break
    if not out["results"]:
        out["blocked"] = True
    return out


def try_humble(title: str, limit: int = 5) -> dict[str, Any]:
    title = (title or "").strip()
    if not title:
        return _empty("")
    return cached(f"humble:v1:{title.lower()}", lambda: _try_humble(title, limit), 1800)


def _try_fanatical(title: str, limit: int = 5) -> dict[str, Any]:
    url = f"https://www.fanatical.com/en/search?search={quote_plus(title)}"
    out: dict[str, Any] = {"results": [], "blocked": False, "search_url": url}
    html, _ = fetch_html(url)
    if not html:
        return _empty(url)
    soup = soup_from(html)
    for card in soup.select("[class*='ProductCard'], article, .hit")[: limit + 12]:
        a = card.find("a", href=True)
        name_el = card.find(["h2", "h3", "span"], class_=lambda c: c and ("title" in str(c).lower() or "name" in str(c).lower()))
        name = (name_el or a).get_text(" ", strip=True) if (name_el or a) else ""
        price_el = card.find(class_=lambda c: c and "price" in str(c).lower())
        price = parse_money(price_el.get_text() if price_el else card.get_text(" ", strip=True))
        href = urljoin(url, a["href"]) if a else url
        row = product_row(name=name, price=price, currency="GBP", url=href, store_name="Fanatical")
        if row:
            out["results"].append(row)
        if len(out["results"]) >= limit:
            break
    if not out["results"]:
        out["blocked"] = True
    return out


def try_fanatical(title: str, limit: int = 5) -> dict[str, Any]:
    title = (title or "").strip()
    if not title:
        return _empty("")
    return cached(f"fanatical:v1:{title.lower()}", lambda: _try_fanatical(title, limit), 1800)


def _try_gmg(title: str, limit: int = 5) -> dict[str, Any]:
    url = f"https://www.greenmangaming.com/search?query={quote_plus(title)}"
    out: dict[str, Any] = {"results": [], "blocked": False, "search_url": url}
    html, _ = fetch_html(url)
    if not html:
        return _empty(url)
    soup = soup_from(html)
    for card in soup.select(".prod-info, .product, article, [class*='product']")[: limit + 12]:
        a = card.find("a", href=True)
        name_el = card.find(["h2", "h3", "a"])
        name = (name_el or a).get_text(" ", strip=True) if (name_el or a) else ""
        price_el = card.find(class_=lambda c: c and "price" in str(c).lower())
        price = parse_money(price_el.get_text() if price_el else card.get_text(" ", strip=True))
        href = urljoin(url, a["href"]) if a else url
        row = product_row(name=name, price=price, currency="GBP", url=href, store_name="Green Man Gaming")
        if row:
            out["results"].append(row)
        if len(out["results"]) >= limit:
            break
    if not out["results"]:
        out["blocked"] = True
    return out


def try_gmg(title: str, limit: int = 5) -> dict[str, Any]:
    title = (title or "").strip()
    if not title:
        return _empty("")
    return cached(f"gmg:v1:{title.lower()}", lambda: _try_gmg(title, limit), 1800)


def _try_gog(title: str, limit: int = 5) -> dict[str, Any]:
    # GOG has a public catalog API-like endpoint sometimes; HTML search fallback
    url = f"https://www.gog.com/en/games?query={quote_plus(title)}"
    out: dict[str, Any] = {"results": [], "blocked": False, "search_url": url}
    html, _ = fetch_html(url)
    if not html:
        return _empty(url)
    soup = soup_from(html)
    for card in soup.select("a.product-tile, .product-tile, [class*='product-tile']")[: limit + 10]:
        a = card if card.name == "a" else card.find("a", href=True)
        name_el = card.find(class_=lambda c: c and "title" in str(c).lower())
        name = (name_el or a).get_text(" ", strip=True) if (name_el or a) else ""
        price_el = card.find(class_=lambda c: c and "price" in str(c).lower())
        price = parse_money(price_el.get_text() if price_el else card.get_text(" ", strip=True))
        href = urljoin(url, a["href"]) if a and a.get("href") else url
        row = product_row(name=name, price=price, currency="GBP", url=href, store_name="GOG")
        if row:
            out["results"].append(row)
        if len(out["results"]) >= limit:
            break
    if not out["results"]:
        out["blocked"] = True
    return out


def try_gog(title: str, limit: int = 5) -> dict[str, Any]:
    title = (title or "").strip()
    if not title:
        return _empty("")
    return cached(f"gog:v1:{title.lower()}", lambda: _try_gog(title, limit), 1800)


def _try_cdkeys(title: str, limit: int = 5) -> dict[str, Any]:
    url = f"https://www.cdkeys.com/?q={quote_plus(title)}"
    out: dict[str, Any] = {"results": [], "blocked": False, "search_url": url}
    html, _ = fetch_html(url)
    if not html:
        return _empty(url)
    soup = soup_from(html)
    for card in soup.select(".product-item, .product, li.item")[: limit + 12]:
        a = card.find("a", href=True)
        name_el = card.find(["h2", "h3", "a", "strong"])
        name = (name_el or a).get_text(" ", strip=True) if (name_el or a) else ""
        price_el = card.find(class_=lambda c: c and "price" in str(c).lower())
        price = parse_money(price_el.get_text() if price_el else card.get_text(" ", strip=True))
        href = urljoin(url, a["href"]) if a else url
        row = product_row(name=name, price=price, currency="GBP", url=href, store_name="CDKeys")
        if row:
            out["results"].append(row)
        if len(out["results"]) >= limit:
            break
    if not out["results"]:
        out["blocked"] = True
    return out


def try_cdkeys(title: str, limit: int = 5) -> dict[str, Any]:
    title = (title or "").strip()
    if not title:
        return _empty("")
    return cached(f"cdkeys:v1:{title.lower()}", lambda: _try_cdkeys(title, limit), 1800)


def fetch_digital_bundle(title: str, limit: int = 4) -> dict[str, Any]:
    title = (title or "").strip()
    links = digital_search_links(title)

    def wrap(fn):
        def run():
            try:
                return fn(title, limit)
            except Exception:
                return _empty("")

        return run

    with ThreadPoolExecutor(max_workers=5) as pool:
        f_h = pool.submit(wrap(try_humble))
        f_f = pool.submit(wrap(try_fanatical))
        f_g = pool.submit(wrap(try_gmg))
        f_gog = pool.submit(wrap(try_gog))
        f_cd = pool.submit(wrap(try_cdkeys))
        return {
            "humble": f_h.result(),
            "fanatical": f_f.result(),
            "gmg": f_g.result(),
            "gog": f_gog.result(),
            "cdkeys": f_cd.result(),
            "digital_links": links,
        }
