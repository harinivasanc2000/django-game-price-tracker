"""
Strict product-title matching for store scrapes and search buckets.

Problem this solves
-------------------
Retail search for "Batman: Arkham Knight" often returns:
  - LEGO Batman
  - Arkham Asylum / Arkham City / Arkham Origins
  - generic "Batman" bundles

Techniques used
---------------
1. Normalize: lowercase, strip edition/platform noise, unify punctuation.
2. Significant tokens only (drop the/and/edition/ps5…).
3. Coverage score: fraction of query tokens present as *whole words* in the listing.
4. Discriminator rule: the rarest / longest query tokens MUST appear.
5. Contaminant rejection: listing-only franchise markers (lego, mobile, …).
6. Known sequel/variant exclusions (God of War vs Ragnarök, etc.).
7. Soft score for ranking (higher = better match).

Pure functions, no network — safe for unit tests.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable

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

_CONTAMINANTS = frozenset(
    {
        "lego", "legos", "mobile", "android", "ios", "free",
        "vr", "pinball", "slot", "slots", "karaoke",
        "comic", "movie", "dvd", "blu", "bluray",
        "soundtrack", "ost", "artbook", "guide",
        "controller", "dualsense", "headset", "skin", "case",
        "figurine", "statue", "plush",
        "telltale", "unofficial", "fan",
    }
)

# When query is the base set and listing has a forbidden sequel token → reject.
_VARIANT_EXCLUSIONS = (
    (frozenset({"god", "war"}), frozenset({"ragnarok"})),
    (frozenset({"last", "us"}), frozenset({"part", "ii", "2"})),
    (frozenset({"spider", "man"}), frozenset({"miles", "morales"})),
    (frozenset({"horizon"}), frozenset({"forbidden", "west"})),
    (frozenset({"assassin", "creed"}), frozenset({"valhalla", "odyssey", "origins", "mirage", "shadows"})),
    (frozenset({"red", "dead", "redemption"}), frozenset({"2", "ii"})),
    (frozenset({"elder", "scrolls"}), frozenset({"online", "skyrim", "oblivion", "morrowind"})),
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")

_ROMAN_NUMERALS = frozenset(
    {
        "i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x",
        "xi", "xii", "xiii", "xiv", "xv", "xvi", "xvii", "xviii", "xix", "xx",
    }
)


def normalize_title(text: str) -> str:
    t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
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
        if len(tok) < 2 and not tok.isdigit() and tok not in _ROMAN_NUMERALS:
            continue
        if tok in _STOP:
            continue
        if tok not in seen:
            seen.add(tok)
            out.append(tok)
    return out


def _whole_word_present(token: str, haystack: str) -> bool:
    return re.search(rf"\b{re.escape(token)}\b", haystack) is not None


def title_match_score(listing_name: str, query_title: str) -> float:
    """0.0 = reject, 1.0 = perfect coverage of query tokens."""
    q_tokens = significant_tokens(query_title)
    if not q_tokens:
        return 1.0

    listing_norm = normalize_title(listing_name)
    if not listing_norm:
        return 0.0

    listing_tokens = set(significant_tokens(listing_name))
    q_set = set(q_tokens)

    sequel_markers = {
        token for token in q_tokens if token.isdigit() or token in _ROMAN_NUMERALS
    }
    if not sequel_markers.issubset(listing_tokens):
        return 0.0

    for c in _CONTAMINANTS:
        if c in listing_tokens and c not in q_set:
            return 0.0

    for base_tokens, forbidden_tokens in _VARIANT_EXCLUSIONS:
        if base_tokens.issubset(q_set) and not (forbidden_tokens & q_set):
            if forbidden_tokens & listing_tokens:
                return 0.0

    hits = [t for t in q_tokens if _whole_word_present(t, listing_norm)]
    if not hits:
        return 0.0

    coverage = len(hits) / len(q_tokens)

    if len(q_tokens) >= 2:
        ranked = sorted(q_tokens, key=lambda t: (-len(t), t))
        must = {ranked[0]}
        if len(q_tokens) >= 3:
            must.add(ranked[1])
        for m in must:
            if not _whole_word_present(m, listing_norm):
                return 0.0

    if len(q_tokens) == 1:
        return 1.0 if hits else 0.0

    if len(q_tokens) == 2 and coverage < 1.0:
        return 0.0
    if len(q_tokens) >= 3 and coverage < 0.67:
        return 0.0

    q_phrase = " ".join(q_tokens[:3])
    if q_phrase and q_phrase in listing_norm:
        coverage = min(1.0, coverage + 0.15)

    return round(coverage, 3)


def titles_match(listing_name: str, query_title: str, *, min_score: float = 0.67) -> bool:
    return title_match_score(listing_name, query_title) >= min_score


def filter_by_title(
    rows: Iterable[dict],
    query_title: str,
    *,
    name_key: str = "name",
    min_score: float = 0.67,
) -> list[dict]:
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
        return (-score, price)

    scored.sort(key=sort_key)
    return [r for _, r in scored]
