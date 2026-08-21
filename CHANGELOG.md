# Changelog

**Rule:** Never overwrite past entries. Always **prepend** new sections at the top (newest first).

---

## 2026-08-21 04:35 BST — Buy guide + public Steam / CheapShark feeds

### Public data (what to buy & where)
- New client `public_deals.py`
  - **Steam** `featuredcategories` (GB): specials, top sellers, new releases
  - **CheapShark** `/deals` sorted by savings (multi-store PC)
- New page **`/guide/`** (nav: **Guide**)
  - Smart picks (≥40% off) with official vs third-party advice
  - Steam specials, multi-store list, top sellers
  - Your tracked list ranked by % under launch
  - Simple buying rules (official first, edition match, physical tips)

### Deals page
- Shows public Steam specials + CheapShark feed **above** tracked rows

### Home
- Live **Steam specials** strip when the public API responds
- Link into the buy guide

### Next backlog
- Sale calendar overlay on charts
- Edition matcher (Standard vs Gold)
- Offline predictions.json display

```bash
git pull && python manage.py runserver
# http://127.0.0.1:8000/guide/
# http://127.0.0.1:8000/deals/
```

---

## 2026-08-21 04:25 BST — Training CSV + detail digital panel wiring

### Added
- `/export/training.csv` for offline ML
- Research download buttons
- Digital store panel + similar games on detail
- Fixed JS HTML escape

---

## 2026-08-20 22:05 BST — Digital BS4 stores + Research lab

- Humble, Fanatical, GMG, GOG, CDKeys scrapers + `/research/`

---

## Earlier

See git log.
