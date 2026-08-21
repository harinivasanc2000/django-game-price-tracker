# Changelog

**Rule:** Never overwrite past entries. Always **prepend** new sections at the top (newest first).

---

## 2026-08-21 19:55 BST — Public scrape filters (eBay + UK + Amazon)

### Filters (no login required)
- **Platform** — already on search/detail; now also soft-filters scraped row titles
- **Min / max £** — applied to UK scrapes, Amazon, official digital, CheapShark
- **Condition** — `new` | `used` | any
  - **eBay**: public URL params `LH_BIN`, `LH_ItemCondition`, `_udlo` / `_udhi`
  - **CeX**: treated as used (hidden when condition=new)
  - Post-scrape filter on all BS4 rows

### Scrapers
- New `apps/games/clients/scrape_filters.py` shared helpers
- eBay BS4 improved: condition from subtitle, filtered search URL always returned
- Amazon / GAME / Argos / Currys / Smyths / CeX run through the same filter pipeline
- UK panel shows active filter badges + condition on eBay rows

### UI
- Partial `templates/games/_deal_filters.html` (platform / condition / min / max)
- Query examples:
  - `/steam/1593500/?platform=ps5&max_price=25&condition=used`
  - `/api/platform/1593500/?platform=ps5&min_price=5&max_price=20&condition=new`

### Tests
- `apps/games/tests/test_scrape_filters.py`

```bash
git pull
python manage.py test apps.games.tests.test_scrape_filters apps.games.tests.test_uk_stores
python manage.py runserver
```

---

## 2026-08-21 19:50 BST — Build on matching + deal links

- Accessory reject list; UK rows sorted by price; platform-aware social links

---

## 2026-08-21 19:05 BST — Graph quality + UK BS4 price matching

- Charts only with real GBP data; title-token matching; HotUKDeals

---

## 2026-08-21 18:45 BST — Deal links, graphs + CDKeys/Loaded resilience

- Loaded (CDKeys) fallback; chronological graphs; hashed cache keys

---

## Earlier

See git log.
