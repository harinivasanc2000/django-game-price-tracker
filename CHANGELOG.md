# Changelog

**Rule:** Never overwrite past entries. Always **prepend** new sections at the top (newest first).

---

## 2026-08-20 21:55 BST — Error hardening + features

### Fixed
- **FX conversion bug**: open.er-api rates are *GBP-base* (1 GBP = N foreign). Now inverted so USD/EUR → GBP is correct (`fx.py` cache key `v2`)
- Detail page no longer 500s if one store scrape / CheapShark / news fails — each future is soft-caught (`views_steam_detail.py`)
- `deal_prediction_panel` catches bad context instead of crashing the template

### Added
- **`/health/`** — DB + beautifulsoup/lxml diagnostics JSON
- **Related on Steam** (`similar_games`) via public storesearch
- `detail_helpers.empty_platform_bundle` fallback
- Template partial `_similar_games.html` (include in sidebar)

### Template tip
In `steam_detail.html` sidebar, add:
```django
{% include "games/_similar_games.html" %}
```
Fix AJAX esc() if still wrong:
```js
function esc(s) {
  return String(s || '')
    .replace(/&/g,'&')
    .replace(/</g,'<')
    .replace(/"/g,'"');
}
```

```bash
git pull && python manage.py runserver
# check: http://127.0.0.1:8000/health/
```

---

## 2026-08-20 21:05 BST — UK local scrapes + clickable links

### Added
- CeX, eBay, GAME, Argos, Currys parallel public search
- Always-clickable uk_links including Facebook Marketplace / Gumtree (link-only)

---

## 2026-08-20 21:02 BST — lxml FeatureNotFound fix

### Fixed
- Fall back to `html.parser` when lxml missing

---

## 2026-08-20 20:35 BST — BeautifulSoup + deal prediction

### Added
- BS4 public product scrape; deal outlook heuristics

---

## Earlier

See git log for appearance settings, home grid, Celery, Steam, PSN, etc.

---

## Backlog

- [ ] Per-user track lists
- [ ] Discord / email alerts
- [ ] Stronger CeX when not blocked
