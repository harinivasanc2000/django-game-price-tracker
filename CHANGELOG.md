# Changelog

**Rule:** Never overwrite past entries. Always **prepend** new sections at the top (newest first).

---

## 2026-08-21 04:25 BST — Training CSV + detail digital panel wiring

### Added
- **`/export/training.csv`** — flat PriceRecord snapshots for offline ML (pandas)
  - Columns: recorded_at, title, steam_app_id, platform, launch, store, price, price_gbp, discount, physical/used, url
  - Optional `?limit=` (default 5000, max 20000)
- Research lab download buttons: CSV, tracked JSON, health

### Detail page
- Included **`_digital_store_links.html`** (Humble / Fanatical / GMG / GOG / CDKeys + meta chips)
- Included **`_similar_games.html`** in sidebar
- Fixed JS `esc()` to real HTML entities (`&` / `<` / `"`)

### Next (backlog)
- Sale calendar overlay on chart
- Load offline `predictions.json` for display only
- Edition matcher (Standard vs Gold vs DLC)
- Bundle vs single price detector

```bash
git pull && python manage.py runserver
# http://127.0.0.1:8000/research/
# http://127.0.0.1:8000/export/training.csv
```

---

## 2026-08-20 22:05 BST — More digital BS4 stores + Research lab

### Scraping (product fields only)
- New client `digital_stores_bs4.py`: **Humble, Fanatical, Green Man Gaming, GOG, CDKeys**
- Always-on search chips: Epic, Eneba, AllKeyShop, GG.deals, ITAD
- Fields: title, price, currency, URL, store name only
- Soft-fail + cache; keyshops labelled risk

### Research lab (`/research/`)
- Separate nav tab for enthusiasts & programmers
- **No ML training on the server** — plan only
- Data sources: APIs, Kaggle, public pages, your exports
- Algorithms: classification, quantiles, boosting, anomaly detection

---

## 2026-08-20 21:55 BST — Error hardening + similar games

### Fixed
- FX er-api inversion; soft-fail detail futures; prediction tag harden

### Added
- `/health/`; related Steam titles

---

## 2026-08-20 21:05 BST — UK local scrapes

### Added
- CeX, eBay, GAME, Argos, Currys + clickable links

---

## Earlier

See git log for FX, BS4, appearance, Celery, Steam, etc.
