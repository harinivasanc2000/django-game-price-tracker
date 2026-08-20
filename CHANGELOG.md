# Changelog

**Rule:** Never overwrite past entries. Always **prepend** new sections at the top (newest first).

---

## 2026-08-20 21:05 BST — UK local scrapes + clickable store links

### Added / expanded
- Parallel public search: **CeX, eBay, GAME, Argos, Currys** (+ Amazon already)
- Always-clickable `uk_links`: CeX, GAME, Argos, Currys, Amazon, eBay, Smyths, **Facebook Marketplace**, Gumtree, X, Reddit
- Product rows link to product URL when scraped; otherwise **Search →** for that shop
- `_uk_physical_panel.html` partial
- Live offer chips include GAME / Argos / Currys when prices found

### Policy
- Facebook Marketplace: **link only** (no scrape)
- Product title / price / public rating / URL only

### Template
Replace the old "UK physical & local" panel in `steam_detail.html` with:
```django
{% include "games/_uk_physical_panel.html" %}
```

```bash
git pull && python manage.py runserver
```

---

## 2026-08-20 21:02 BST — Fix FeatureNotFound: lxml missing

### Fixed
- Fall back to `html.parser` when lxml not installed

---

## 2026-08-20 20:35 BST — BeautifulSoup + deal prediction

### Added
- BS4 public product scrape helpers; deal outlook heuristics

---

## 2026-08-20 20:05 BST — Appearance settings

### Added
- Themes / wallpapers Settings page; drawer icons

---

## Earlier history

See git history for full prior entries (home grid, deals, Celery, Steam, PSN, etc.).

---

## Backlog

- [ ] Per-user track lists
- [ ] Discord / email alerts
- [ ] Confirm detail template includes `_uk_physical_panel.html`
