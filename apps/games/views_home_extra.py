"""Helpers for home page enrichment."""
from __future__ import annotations

from .models import BrowseHistory


def recent_views_for_session(session_key: str, limit: int = 8) -> list[dict]:
    if not session_key:
        return []
    rows = (
        BrowseHistory.objects.filter(
            session_key=session_key,
            action=BrowseHistory.Action.VIEW,
        )
        .order_by("-created_at")[:40]
    )
    seen = set()
    out = []
    for r in rows:
        key = r.steam_app_id or r.detail_url or r.title
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "title": r.title or "Game",
                "app_id": r.steam_app_id,
                "url": r.detail_url or (f"/steam/{r.steam_app_id}/" if r.steam_app_id else ""),
                "when": r.created_at,
            }
        )
        if len(out) >= limit:
            break
    return out
