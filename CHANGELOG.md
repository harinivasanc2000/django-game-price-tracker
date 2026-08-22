# Changelog

**Rule:** Never overwrite past entries. Always **prepend** new sections at the top (newest first).

---

## 2026-08-22 19:50 BST — UK physical scrapers fixed + optimised

### CeX
- Switched from fragile HTML scrape → **public boxes JSON API**
  (`https://wss2.cex.uk.webuy.io/v3/boxes`)
- Faster, structured `sellPrice` / `boxName` / stock; still title-filtered

### Shared scrape layer
- Stronger browser-like headers (Accept-Language, Sec-Fetch-*, gzip)
- Connection pool 12 (matches 6 parallel UK workers)
- `fetch_json()` helper for API stores
- `extract_ld_json_products()` — real JSON-LD Product/ItemList parse (GAME / Currys / Smyths / Argos)
- HTML timeout **7s** per store; bundle hard deadline **8s** (`wait=False` shutdown)

### Per-store clean-up
- Shared card + ld+json helpers → less duplicated selector code
- Over-fetch ×3 → strict `title_match` → limit (relevance not truncated)
- Cache keys bumped (`cex:v6`, `ebay:v6`, `gameuk:v6`, …)

### Still soft-fail
Any blocked retailer keeps a clickable **search_url** in the UK panel.

```bash
git pull
python manage.py runserver
# open a game detail → UK physical panel
```

---

## 2026-08-22 19:35 BST — Strict title matching (no LEGO on Arkham Knight)

- Coverage score + contaminant reject + discriminator tokens

---

## 2026-08-21 19:55 BST — Public scrape filters

- Platform / min-max £ / condition; eBay URL params

---

## Earlier

See git log.
