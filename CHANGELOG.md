# Changelog

**Rule:** Never overwrite past entries. Always **prepend** new sections at the top (newest first).

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
- Feature ideas: sale calendar, wait curves, training CSV export, model cards
- Workflow: collect → train offline → publish prediction JSON later

### Template
Detail page: include `{% include "games/_digital_store_links.html" %}` under PC deals if missing.

```bash
git pull && python manage.py runserver
# http://127.0.0.1:8000/research/
```

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
