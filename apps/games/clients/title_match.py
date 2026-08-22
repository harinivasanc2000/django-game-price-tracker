"""
Strict product-title matching for store scrapes and search buckets.

Problem this solves
-------------------
Retail search for "Batman: Arkham Knight" often returns:
  - LEGO Batman
  - Arkham Asylum / Arkham City / Arkham Origins
  - generic "Batman" bundles

Old matcher only needed 2 shared tokens → "batman" + anything could pass.

Techniques used
---------------
1. Normalize: lowercase, strip edition/platform noise, unify punctuation.
2. Significant tokens only (drop the/and/edition/ps5…).
3. Coverage score: fraction of query tokens present as *whole words* in the listing.
4. Discriminator rule: the rarest / longest query tokens (e.g. "knight") MUST appear
   when the title has 2+ significant words — stops Asylum/City/Origins bleed.
5. Contaminant rejection: listing-only franchise markers (lego, mobile, …) that are
   NOT in the query → hard reject.
6. Optional soft score for ranking (higher = better match).

Pure functions, no network — safe for unit tests.
"""

from __future__ import annotations

import re
from typing import Iterable

# Noise that never identifies a specific game
_STOP = frozenset(
    {
        "the", "and", "for", "with", "from", "of", "a", "an", "or",
        "game", "games", "video", "videogame",
        "edition", "standard", "deluxe", "ultimate", "complete", "goty",
        "year", "remastered", "remaster", "definitive", "enhanced", "hd",
        "collection", "bundle", "pack", "dlc", "season", "pass",
        "digital", "code", "key", "download", "physical", "disc", "disk",
        "new", "used", "pre", "owned", "preowned", "sealed", "brand",
        "ps3", "ps4", "ps5", "xbox", "one", "series", "switch", "nintendo",
        "playstation", "sony", "microsoft", "pc", "steam", "windows",
        "uk", "eu", "pal", "ntsc", "region",
        "volume", "vol", "part",
    }
)

# If these appear in the *listing* but NOT in the *query*, treat as different product
_CONTAMINANTS = frozenset(
    {
        "lego", "legos", "mobile", "android", "ios", "free",
        "vr", "pinball", "slot", "slots", "karaoke",
        "comic", "movie", "dvd", "blu", "bluray",
        "soundtrack", "ost", "artbook", "guide",
        "controller", "dualsense", "headset", "skin", "case",
        "figurine", "statue", "plush",
    }
)

# Subtitle / entry discriminators often shared across a franchise
# (used only as a hint for weighting — coverage still primary)
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def normalize_title(text: str) -> str:
    t = (text or "").lower()
    t = t.replace("&", " and ")
    t = t.replace("'", "").replace("’", "")
    t = re.sub(r"[:/|_–—·•]+", " ", t)
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def significant_tokens(text: str) -> list[str]:
    """Ordered unique-ish significant tokens from a title."""
    seen: set[str] = set()
    out: list[str] = []
    for tok in _TOKEN_RE.findall(normalize_title(text)):
        if len(tok) < 2:
            continue
        if tok in _STOP:
            continue
        if tok.isdigit() and len(tok) == 4:  # years
            continue
        if tok not in seen:
            seen.add(tok)
            out.append(tok)
    return out


def _whole_word_present(token: str, haystack: str) -> bool:
    """Require token as a whole word (batman ≠ bat)."""
    return re.search(rf"\b{re.escape(token)}\b", haystack) is not None


def title_match_score(listing_name: str, query_title: str) -> float:
    """
    0.0 = reject, 1.0 = perfect coverage of query tokens.

    Scoring rules (all must pass contaminant + discriminator checks first):
      base = (# query tokens found in listing) / (# query tokens)
      bonus if normalized listing startswith main query phrase
    """
    q_tokens = significant_tokens(query_title)
    if not q_tokens:
        return 1.0  # nothing to enforce

    listing_norm = normalize_title(listing_name)
    if not listing_norm:
        return 0.0

    listing_tokens = set(significant_tokens(listing_name))

    # --- Contaminants: LEGO Batman when query is Arkham Knight ---
    q_set = set(q_tokens)
    for c in _CONTAMINANTS:
        if c in listing_tokens and c not in q_set:
            return 0.0

    # --- Coverage of query tokens (whole-word) ---
    hits = [t for t in q_tokens if _whole_word_present(t, listing_norm)]
    if not hits:
        return 0.0

    coverage = len(hits) / len(q_tokens)

    # --- Discriminator: when title has 2+ significant words, require the
    #     longest unique-ish tokens (usually the subtitle: knight, asylum…)
    if len(q_tokens) >= 2:
        # Sort by length desc — "knight" / "arkham" beat "batman" ties on length
        ranked = sorted(q_tokens, key=lambda t: (-len(t), t))
        # Require the longest token always
        must = {ranked[0]}
        # And the second-longest if we have 3+ tokens (e.g. arkham + knight)
        if len(q_tokens) >= 3:
            must.add(ranked[1])
        for m in must:
            if not _whole_word_present(m, listing_norm):
                return 0.0

    # Single-token query (e.g. "Hades"): need exact whole-word hit only — already have
    if len(q_tokens) == 1:
        return 1.0 if hits else 0.0

    # Need solid coverage: 2 tokens → both; 3+ → at least ~67%
    if len(q_tokens) == 2 and coverage < 1.0:
        return 0.0
    if len(q_tokens) >= 3 and coverage < 0.67:
        return 0.0

    # Soft boost if the listing clearly leads with the same phrase
    q_phrase = " ".join(q_tokens[:3])
    if q_phrase and q_phrase in listing_norm:
        coverage = min(1.0, coverage + 0.15)

    return round(coverage, 3)


def titles_match(listing_name: str, query_title: str, *, min_score: float = 0.67) -> bool:
    """Binary keep/drop used by scrapers."""
    return title_match_score(listing_name, query_title) >= min_score


def filter_by_title(
    rows: Iterable[dict],
    query_title: str,
    *,
    name_key: str = "name",
    min_score: float = 0.67,
) -> list[dict]:
    """Keep rows that match; attach match_score; sort best match then price."""
    scored: list[tuple[float, dict]] = []
    for row in rows or []:
        name = row.get(name_key) or ""
        score = title_match_score(name, query_title)
        if score < min_score:
            continue
        enriched = dict(row)
        enriched["match_score"] = score
        scored.append((score, enriched))

    def sort_key(item: tuple[float, dict]):
        score, row = item
        try:
            price = float(row["price"]) if row.get("price") is not None else 999999.0
        except (TypeError, ValueError):
            price = 999999.0
        # Higher score first, then cheaper
        return (-score, price)

    scored.sort(key=sort_key)
    return [r for _, r in scored]
