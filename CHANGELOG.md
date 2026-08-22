# Changelog

**Rule:** Never overwrite past entries. Always **prepend** new sections at the top (newest first).

---

## 2026-08-22 19:35 BST — Strict title matching (no LEGO on Arkham Knight)

### Bug
Retail search for **Batman: Arkham Knight** could show LEGO Batman, Arkham Asylum/City/Origins, and other franchise noise because the old matcher only needed ~2 shared tokens ("batman" was enough noise).

### Fix — `apps/games/clients/title_match.py`
Techniques:
1. **Normalize** titles (punctuation, editions, platforms stripped from token set)
2. **Significant tokens** only (stopword list)
3. **Whole-word** hits (batman ≠ bat)
4. **Coverage score** — need ~all tokens for 2-word titles, ≥67% for longer ones
5. **Discriminator rule** — longest tokens (e.g. `knight`, `arkham`) must appear when the query has 2+ words → blocks Asylum/City/Origins
6. **Contaminant rejection** — listing has `lego` / `mobile` / … but query does not → hard reject
7. **Over-fetch then filter** on UK scrapers + multi-platform search so the limit is applied *after* relevance

Wired into: UK BS4 stores, Amazon filter pipeline, `multi_platform_search` (PSN/Xbox/Nintendo/Steam buckets).

### Tests
- `test_title_match.py` — Arkham Knight vs LEGO / Asylum / City / Origins
- Updated `test_uk_stores.py`

```bash
git pull
python manage.py test apps.games.tests.test_title_match apps.games.tests.test_uk_stores
python manage.py runserver
# reopen Arkham Knight detail — UK / Amazon rows should not list LEGO Batman
```

---

## 2026-08-21 19:55 BST — Public scrape filters (eBay + UK + Amazon)

- Platform / min-max £ / condition filters; eBay public URL params

---

## 2026-08-21 19:50 BST — Build on matching + deal links

- Accessory reject list; platform-aware social links

---

## Earlier

See git log.
