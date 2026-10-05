# Changelog

**Rule:** Never overwrite past entries. Always **prepend** new sections at the top (newest first).

---

## 2026-10-05 — Fix Celery refresh + stronger franchise guards

### Bug fix (critical)
- **`refresh_one_game` was broken**: called `best_psn_deal` / `search_amazon_uk` without imports, so Celery track refreshes soft-failed every non-Steam source
- Rewrote refresh to use the same **`platform_bundle`** path as the detail page (PSN, Xbox, Nintendo, Amazon, all UK locals + specialists)
- Writes the **cheapest in-stock** snapshot per retailer; CheapShark remains optional third-party
- Summary now counts real source hits instead of assuming only PSN+Amazon

### Title matching
- Expanded variant exclusions: Spider-Man vs Miles Morales, Horizon Zero Dawn vs Forbidden West, Assassin’s Creed entries, RDR / Elder Scrolls guards
- Extra contaminants: telltale, unofficial, fan
- New regression tests for Miles Morales and Horizon

```bash
git pull
python manage.py test apps.games.tests.test_title_match
python manage.py runserver
```

---

## 2026-08-28 — UK/BS4, advanced search, graphs, and full polish

See prior entries / git log.
