# Changelog

**Rule:** Never overwrite past entries. Always **prepend** new sections at the top (newest first).

---

## 2026-08-24 07:15 BST — Local stores fix + features

### Fixes
- **CeX**: game-category preference, **in-stock first**, trade-in cash badge, proper `quote_plus` search URL
- Bundle deadline **9s** / 7 parallel workers (added MusicMagpie)
- Cache keys bumped so old empty CeX/HTML results are not sticky

### New features
- **MusicMagpie** used-games public search (soft-fail + link)
- **Cheapest local** strip — merges all UK sources, sorted by price, deduped
- **Store health** line: `3/7 local sources returned prices`
- CeX rows show **in stock** + **sell £X** (trade-in) when API provides them
- MusicMagpie included in live-offer chips

### Panel
- `_uk_physical_panel.html` redesigned: best-local block on top, then per-store rows

```bash
git pull
python manage.py runserver
# open any detail → UK physical panel
```

---

## 2026-08-22 19:50 BST — UK physical scrapers fixed + optimised

- CeX JSON API; ld+json; tighter timeouts

---

## 2026-08-22 19:35 BST — Strict title matching

- No LEGO on Arkham Knight; coverage + contaminants

---

## Earlier

See git log.
