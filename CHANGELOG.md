# Changelog

**Rule:** Never overwrite past entries. Always **prepend** new sections at the top (newest first).

---

## 2026-08-24 07:35 BST — BS4 policy locked in

### Rule (always)
- Local / retail sites **without a public API** → **BeautifulSoup** on the public search page
- If an unofficial JSON endpoint is **blocked or empty** → **BS4 HTML fallback** of the same search URL
- Soft-fail still keeps clickable `search_url`

### CeX
- API first (`wss2…/boxes`)
- On block/empty → BS4 of `uk.webuy.com/search` (embedded JSON + product cards)

Documented in `scrape_utils.py` module docstring so future stores follow the same path.

```bash
git pull
python manage.py runserver
```

---

## 2026-08-24 07:15 BST — Local stores fix + features

- MusicMagpie, cheapest-local strip, CeX stock/trade-in, store health

---

## Earlier

See git log.
