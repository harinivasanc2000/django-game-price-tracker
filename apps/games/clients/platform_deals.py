"""Small, cached public deal feeds for the home-page platform switcher.

Only public sale pages are read.  Parsing is intentionally separate from
network access so fixtures can cover retailer markup without making requests.
Each platform family stores one compact parsed payload in Django's cache; PS4
and PS5 therefore share one download of the PlayStation page.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re
from typing import Any, Iterable

from apps.games.cache import cached
from apps.games.clients.scrape_utils import (
    fetch_html,
    normalise_public_url,
    parse_money,
    soup_from,
)


PLAYSTATION_DEALS_URL = "https://psndeal.com/gb"
XBOX_DEALS_URL = "https://www.xbox.com/en-gb/promotions/sales/sales-and-specials"
SWITCH_DEALS_URL = "https://ntprices.com/"

DEALS_CACHE_TTL = 900
DEALS_EMPTY_TTL = 90
MAX_DEALS = 12
MAX_CANDIDATES = 240
MAX_PRICE = Decimal("1000000")

_FAMILY_BY_PLATFORM = {
    "ps4": "playstation",
    "ps5": "playstation",
    "xbox": "xbox",
    "switch": "switch",
}
_FAMILY_URLS = {
    "playstation": PLAYSTATION_DEALS_URL,
    "xbox": XBOX_DEALS_URL,
    "switch": SWITCH_DEALS_URL,
}

_GBP_RE = re.compile(
    r"(?:£|\bGBP\s*)(?P<before>(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?)"
    r"|(?P<after>(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?)\s*\bGBP\b",
    re.IGNORECASE,
)
_DISCOUNT_RE = re.compile(r"(?<!\d)(\d{1,3})\s*%(?:\s*OFF\b)?", re.IGNORECASE)


def _clean_text(value: Any, *, limit: int = 200) -> str:
    """Collapse remote whitespace/control characters and bound card text."""
    text = " ".join(str(value or "").split())
    return "".join(char for char in text if ord(char) >= 32)[:limit].strip()


def _finite_gbp(value: Any) -> Decimal | None:
    """Return a JSON-safe-range GBP value; reject NaN, infinity and negatives."""
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not amount.is_finite() or amount < 0 or amount > MAX_PRICE:
        return None
    return amount


def _money_from(element) -> Decimal | None:
    if element is None:
        return None
    amount = parse_money(element.get_text(" ", strip=True), require_currency=True)
    return _finite_gbp(amount)


def _original_money_from(element) -> Decimal | None:
    """Read a crossed-out amount without ``parse_money`` discarding "was" text."""
    if element is None:
        return None
    values = _gbp_values(element.get_text(" ", strip=True))
    return values[0] if values else None


def _gbp_values(text: str) -> list[Decimal]:
    """Extract only explicitly GBP-marked values from a mixed card string."""
    values: list[Decimal] = []
    for match in _GBP_RE.finditer(str(text or "").replace("\xa0", " ")):
        amount = _finite_gbp((match.group("before") or match.group("after") or "").replace(",", ""))
        if amount is not None:
            values.append(amount)
    return values


def _discount_from(text: str) -> int | None:
    for match in _DISCOUNT_RE.finditer(str(text or "")):
        try:
            discount = int(match.group(1))
        except (TypeError, ValueError):
            continue
        if 1 <= discount <= 100:
            return discount
    return None


def _other_price(
    container,
    original: Decimal | None,
    *,
    prefer_last: bool = False,
) -> Decimal | None:
    """Find the sale value beside an old price when CSS names are unstable.

    PSNDeal and NTPrices render sale then original, while Xbox renders original
    then sale.  Source-specific callers choose the appropriate direction.
    """
    if container is None:
        return None
    values = _gbp_values(container.get_text(" ", strip=True))
    if original is not None:
        values = [value for value in values if value != original]
    if not values:
        return None
    return values[-1] if prefer_last else values[0]


def _safe_image(element, *, base_url: str, allowed_hosts: Iterable[str]) -> str:
    if element is None:
        return ""
    raw = element.get("src") or element.get("data-src") or element.get("data-original") or ""
    return normalise_public_url(raw, base_url=base_url, allowed_hosts=allowed_hosts)


def _normalised_deal(
    *,
    title: str,
    platform: str,
    current: Any,
    original: Any,
    discount_hint: int | None,
    image: str,
    url: str,
    store_name: str,
    source_kind: str,
) -> dict[str, Any] | None:
    """Validate a source row and convert Decimal values to JSON primitives."""
    title = _clean_text(title)
    current_price = _finite_gbp(current)
    original_price = _finite_gbp(original)
    if not title or current_price is None or not url:
        return None

    # A crossed-out amount at or below the current value is not a valid sale.
    # When both prices exist, derive the percentage from them instead of
    # trusting a decorative badge that may belong to another card.
    if original_price is not None:
        if original_price <= current_price or original_price == 0:
            return None
        discount = int(round((Decimal("1") - current_price / original_price) * 100))
    else:
        discount = discount_hint or 0
    if not 1 <= discount <= 100:
        return None

    return {
        "title": title,
        "platform": platform,
        "price_gbp": float(current_price),
        "original_gbp": float(original_price) if original_price is not None else None,
        "discount": discount,
        "image": image,
        "url": url,
        "store_name": store_name,
        "source_kind": source_kind,
    }


def _dedupe_and_cap(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep source order while removing repeated cards from page sections."""
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        marker = (str(row.get("platform") or ""), str(row.get("title") or "").casefold())
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(row)
        if len(unique) >= MAX_DEALS:
            break
    return unique


def parse_playstation_deals(html: str, platform: str) -> list[dict[str, Any]]:
    """Parse PSNDeal's server-rendered UK sale cards for PS4 or PS5."""
    platform = str(platform or "").strip().lower()
    if platform not in {"ps4", "ps5"} or not isinstance(html, str) or not html.strip():
        return []
    try:
        # Some React streaming responses contain NUL separators; they carry no
        # markup meaning and can upset an otherwise valid BeautifulSoup parse.
        soup = soup_from(html.replace("\x00", ""))
        rows: list[dict[str, Any]] = []
        candidates = soup.select("a[href*='/game/']")[:MAX_CANDIDATES]
        for card in candidates:
            labels: set[str] = set()
            for element in card.find_all(["span", "div"]):
                label = _clean_text(element.get_text(" ", strip=True), limit=32).upper()
                if len(label) <= 16:
                    labels.update(re.findall(r"\bPS[45]\b", label))
            if platform.upper() not in labels:
                continue

            title_element = card.select_one("h3, h2, .game-name, [class*='title']")
            image_element = card.find("img")
            title = (
                title_element.get_text(" ", strip=True)
                if title_element is not None
                else (image_element.get("alt") if image_element is not None else "")
            )
            original_element = card.select_one(
                ".line-through, .strike-price, [class*='original-price'], s, del"
            )
            original = _original_money_from(original_element)
            if original_element is not None and original is None:
                continue
            current_element = card.select_one(
                ".text-base.font-bold, .sale-price, .current-price, [class*='price-current']"
            )
            current = _money_from(current_element)
            if current is None:
                current = _other_price(
                    original_element.parent if original_element is not None else card,
                    original,
                )

            url = normalise_public_url(
                card.get("href"),
                base_url=PLAYSTATION_DEALS_URL,
                allowed_hosts=("psndeal.com",),
            )
            image = _safe_image(
                image_element,
                base_url=PLAYSTATION_DEALS_URL,
                allowed_hosts=("psndeal.com", "bysxynqpjhlmaycmnpmb.supabase.co"),
            )
            row = _normalised_deal(
                title=title,
                platform=platform,
                current=current,
                original=original,
                discount_hint=_discount_from(card.get_text(" ", strip=True)),
                image=image,
                url=url,
                store_name="PSNDeal",
                source_kind="aggregator",
            )
            if row is not None:
                rows.append(row)
        return _dedupe_and_cap(rows)
    except Exception:
        return []


def parse_xbox_deals(html: str) -> list[dict[str, Any]]:
    """Parse game offers from Xbox's official UK sales page."""
    if not isinstance(html, str) or not html.strip():
        return []
    try:
        soup = soup_from(html.replace("\x00", ""))
        rows: list[dict[str, Any]] = []
        candidates = soup.select(
            "a.gameDivLink[href], section.gameDiv a[href], a[href*='/games/store/']"
        )[:MAX_CANDIDATES]
        for card in candidates:
            url = normalise_public_url(
                card.get("href"),
                base_url=XBOX_DEALS_URL,
                allowed_hosts=("xbox.com",),
            )
            if not url or "/games/store/" not in url.lower():
                continue

            # The same page also advertises PC-only products and hardware.  A
            # platform badge, when present, must explicitly include console.
            platform_badges = card.select(".badge-silver, [class*='platform']")
            platform_text = " ".join(item.get_text(" ", strip=True) for item in platform_badges)
            if platform_text and "CONSOLE" not in platform_text.upper():
                continue

            title_element = card.select_one(".x1GameName, h3, h2, [class*='game-name']")
            image_element = card.find("img")
            title = (
                title_element.get_text(" ", strip=True)
                if title_element is not None
                else (image_element.get("alt") if image_element is not None else "")
            )
            title = re.sub(r"^Box (?:shot|art) of\s+", "", str(title), flags=re.IGNORECASE)
            original_element = card.select_one(".strike-price, s, del, [class*='original-price']")
            original = _original_money_from(original_element)
            if original_element is not None and original is None:
                continue
            current_element = card.select_one(
                ".textpricenew, .sale-price, .current-price, [class*='price-new']"
            )
            current = _money_from(current_element)
            if current is None:
                price_container = card.select_one(".c-price, [class*='price']") or card
                current = _other_price(price_container, original, prefer_last=True)

            image = _safe_image(
                image_element,
                base_url=XBOX_DEALS_URL,
                allowed_hosts=(
                    "xbox.com",
                    "s-microsoft.com",
                    "xboxservices.com",
                ),
            )
            row = _normalised_deal(
                title=title,
                platform="xbox",
                current=current,
                original=original,
                discount_hint=_discount_from(card.get_text(" ", strip=True)),
                image=image,
                url=url,
                store_name="Xbox / Microsoft Store",
                source_kind="official",
            )
            if row is not None:
                rows.append(row)
        return _dedupe_and_cap(rows)
    except Exception:
        return []


def parse_switch_deals(html: str) -> list[dict[str, Any]]:
    """Parse current UK Switch/Switch 2 discounts from NTPrices."""
    if not isinstance(html, str) or not html.strip():
        return []
    try:
        soup = soup_from(html.replace("\x00", ""))
        rows: list[dict[str, Any]] = []
        candidates = soup.select("a.game-container[href], a[href*='/game/']")[:MAX_CANDIDATES]
        for card in candidates:
            url = normalise_public_url(
                card.get("href"),
                base_url=SWITCH_DEALS_URL,
                allowed_hosts=("ntprices.com",),
            )
            if not url:
                continue
            image_element = card.find("img")
            title_element = card.select_one(".game-name, h3, h2, [class*='game-title']")
            title = (
                title_element.get_text(" ", strip=True)
                if title_element is not None
                else (image_element.get("alt") if image_element is not None else "")
            )
            original_element = card.select_one(".strike-price, .was, s, del")
            original = _original_money_from(original_element)
            if original_element is not None and original is None:
                continue
            current_element = card.select_one(".now, .current-price, .sale-price")
            current = _money_from(current_element)
            if current is None:
                price_container = card.select_one(".game-price, [class*='price']") or card
                current = _other_price(price_container, original)

            image = _safe_image(
                image_element,
                base_url=SWITCH_DEALS_URL,
                allowed_hosts=("ntprices.com", "imgcdn.platprices.com"),
            )
            row = _normalised_deal(
                title=title,
                platform="switch",
                current=current,
                original=original,
                discount_hint=_discount_from(card.get_text(" ", strip=True)),
                image=image,
                url=url,
                store_name="NTPrices",
                source_kind="aggregator",
            )
            if row is not None:
                rows.append(row)
        return _dedupe_and_cap(rows)
    except Exception:
        return []


def _fetch_family(family: str) -> list[dict[str, Any]]:
    """Download and parse one known source; never propagate a source failure."""
    url = _FAMILY_URLS.get(family)
    if not url:
        return []
    try:
        html, _status = fetch_html(url, timeout=10)
    except Exception:
        return []
    if not html:
        return []
    if family == "playstation":
        return parse_playstation_deals(html, "ps4") + parse_playstation_deals(html, "ps5")
    if family == "xbox":
        return parse_xbox_deals(html)
    if family == "switch":
        return parse_switch_deals(html)
    return []


def console_deals(platform: str, limit: int = MAX_DEALS) -> list[dict[str, Any]]:
    """Return a small cached deal feed for one supported console platform."""
    platform = str(platform or "").strip().lower()
    family = _FAMILY_BY_PLATFORM.get(platform)
    if family is None:
        return []
    try:
        requested = int(limit)
    except (TypeError, ValueError, OverflowError):
        requested = MAX_DEALS
    if requested <= 0:
        return []
    requested = min(requested, MAX_DEALS)

    try:
        # Family-level identity is important: simultaneous PS4 and PS5 requests
        # collapse into one public-page download via cached()'s single flight.
        rows = cached(
            f"console-deals:v1:{family}",
            lambda: _fetch_family(family),
            DEALS_CACHE_TTL,
            empty_timeout=DEALS_EMPTY_TTL,
        )
    except Exception:
        return []
    return [dict(row) for row in rows if row.get("platform") == platform][:requested]
