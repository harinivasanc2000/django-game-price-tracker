"""
Game news & social chatter helpers.

- Steam has a public news API per appid (no key).
- X/Twitter, Reddit, Facebook are link-outs (no unofficial API scrape).
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus

import requests

from apps.games.cache import cached

STEAM_NEWS = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/"


def _steam_news_uncached(app_id: int, count: int = 6) -> list[dict[str, Any]]:
    try:
        r = requests.get(
            STEAM_NEWS,
            params={"appid": app_id, "count": count, "maxlength": 180, "format": "json"},
            timeout=12,
            headers={"User-Agent": "GamePriceTracker/0.1"},
        )
        r.raise_for_status()
        items = (r.json().get("appnews") or {}).get("newsitems") or []
    except (requests.RequestException, ValueError, TypeError):
        return []

    out = []
    for n in items[:count]:
        out.append(
            {
                "title": n.get("title") or "News",
                "url": n.get("url") or n.get("feedlabel") or "",
                "date": n.get("date"),
                "feed": n.get("feedlabel") or n.get("feedname") or "Steam",
                "summary": (n.get("contents") or "")[:200],
            }
        )
    return out


def steam_news(app_id: int, count: int = 6) -> list[dict[str, Any]]:
    return cached(
        f"steam:news:{app_id}:{count}",
        lambda: _steam_news_uncached(app_id, count=count),
        timeout=900,  # 15 min
    )


def social_news_links(title: str) -> list[dict[str, str]]:
    q = quote_plus(title)
    deal_q = quote_plus(f"{title} (deal OR sale OR discount OR free)")
    return [
        {
            "name": "X · deals & chatter",
            "url": f"https://x.com/search?q={deal_q}&src=typed_query&f=live",
        },
        {
            "name": "Reddit · r/GameDeals search",
            "url": f"https://www.reddit.com/r/GameDeals/search/?q={q}&restrict_sr=1&sort=new",
        },
        {
            "name": "Reddit · r/PS5 search",
            "url": f"https://www.reddit.com/r/PS5/search/?q={q}&restrict_sr=1&sort=new",
        },
        {
            "name": "Facebook · posts search",
            "url": f"https://www.facebook.com/search/posts/?q={q}",
        },
    ]
