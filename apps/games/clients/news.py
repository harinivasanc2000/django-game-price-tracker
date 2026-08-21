"""
Game news & social chatter helpers.

- Steam public news API per appid (no key).
- Prefer items about sales, discounts, free weekends, price.
- X/Twitter, Reddit, Facebook are link-outs only.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus

import requests

from apps.games.cache import cached

STEAM_NEWS = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/"

DEAL_KEYWORDS = (
    "sale",
    "sales",
    "discount",
    "discounts",
    "deal",
    "deals",
    "free",
    "weekend",
    "price",
    "priced",
    "offer",
    "offers",
    "promo",
    "promotion",
    "bundle",
    "% off",
    "percent off",
    "half-price",
    "half price",
    "launch price",
    "msrp",
    "reduced",
    "cheaper",
    "giveaway",
    "free to play",
    "free weekend",
    "on sale",
    "now free",
)


def _is_deal_related(title: str, summary: str = "") -> bool:
    text = f"{title} {summary}".lower()
    return any(k in text for k in DEAL_KEYWORDS)


def _steam_news_uncached(app_id: int, count: int = 8, deals_only: bool = True) -> list[dict[str, Any]]:
    fetch_n = max(count * 4, 20) if deals_only else count
    try:
        r = requests.get(
            STEAM_NEWS,
            params={"appid": app_id, "count": fetch_n, "maxlength": 220, "format": "json"},
            timeout=12,
            headers={"User-Agent": "GamePriceTracker/0.1"},
        )
        r.raise_for_status()
        items = (r.json().get("appnews") or {}).get("newsitems") or []
    except (requests.RequestException, ValueError, TypeError):
        return []

    out = []
    for n in items:
        title = n.get("title") or "News"
        summary = (n.get("contents") or "")[:220]
        if deals_only and not _is_deal_related(title, summary):
            continue
        out.append(
            {
                "title": title,
                "url": n.get("url") or "",
                "date": n.get("date"),
                "feed": n.get("feedlabel") or n.get("feedname") or "Steam",
                "summary": summary,
                "deal_related": True,
            }
        )
        if len(out) >= count:
            break

    if deals_only and not out:
        for n in items[: min(3, count)]:
            out.append(
                {
                    "title": n.get("title") or "News",
                    "url": n.get("url") or "",
                    "date": n.get("date"),
                    "feed": n.get("feedlabel") or n.get("feedname") or "Steam",
                    "summary": (n.get("contents") or "")[:200],
                    "deal_related": False,
                }
            )
    return out


def steam_news(app_id: int, count: int = 6, deals_only: bool = True) -> list[dict[str, Any]]:
    return cached(
        f"steam:news:deals:{app_id}:{count}:{int(deals_only)}",
        lambda: _steam_news_uncached(app_id, count=count, deals_only=deals_only),
        timeout=900,
    )


def social_news_links(title: str, platform: str = "") -> list[dict[str, str]]:
    """Link-outs only. Platform filter prioritises relevant subreddits."""
    q = quote_plus(title)
    deal_q = quote_plus(f'{title} (deal OR sale OR discount OR free OR "on sale")')
    plat = (platform or "").strip().lower()

    links = [
        {
            "name": "X · deals & chatter",
            "url": f"https://x.com/search?q={deal_q}&src=typed_query&f=live",
        },
        {
            "name": "Reddit · r/GameDeals",
            "url": f"https://www.reddit.com/r/GameDeals/search/?q={q}&restrict_sr=1&sort=new",
        },
        {
            "name": "HotUKDeals · newest",
            "url": f"https://www.hotukdeals.com/search?q={q}&sort=latest",
        },
    ]

    if plat in ("", "ps4", "ps5"):
        links.append(
            {
                "name": "Reddit · r/PS5",
                "url": f"https://www.reddit.com/r/PS5/search/?q={q}&restrict_sr=1&sort=new",
            }
        )
    if plat in ("", "xbox"):
        links.append(
            {
                "name": "Reddit · r/XboxGamePass",
                "url": f"https://www.reddit.com/r/XboxGamePass/search/?q={q}&restrict_sr=1&sort=new",
            }
        )
    if plat in ("", "switch"):
        links.append(
            {
                "name": "Reddit · r/NintendoSwitchDeals",
                "url": f"https://www.reddit.com/r/NintendoSwitchDeals/search/?q={q}&restrict_sr=1&sort=new",
            }
        )
    if plat in ("", "pc"):
        links.append(
            {
                "name": "Reddit · r/SteamDeals",
                "url": f"https://www.reddit.com/r/steamdeals/search/?q={q}&restrict_sr=1&sort=new",
            }
        )

    links.extend(
        [
            {
                "name": "IsThereAnyDeal",
                "url": f"https://isthereanydeal.com/search/?q={q}",
            },
            {
                "name": "GG.deals",
                "url": f"https://gg.deals/games/?title={q}",
            },
        ]
    )
    return links
