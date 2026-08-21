# Django Game Price Tracker

Personal **Django** app to compare **public** game prices (Steam, CheapShark multi-store, PSN, UK shops) and track drops.

Not a store. Not financial advice. Confirm every price on the seller’s site.

---

## Quick start

```bash
git clone https://github.com/harinivasanc2000/django-game-price-tracker.git
cd django-game-price-tracker
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_launch_prices   # optional
python manage.py runserver
```

Or: `chmod +x run.sh && ./run.sh`

Open http://127.0.0.1:8000/

---

## Main pages

| URL | Purpose |
|-----|--------|
| `/` | Popular titles + Steam specials |
| `/search/` | Steam search |
| `/steam/<app_id>/` | Multi-store compare + chart + track |
| `/guide/` | What to buy & where (public feeds) |
| `/deals/` | Public deals + your tracked list |
| `/research/` | Offline ML notes + CSV export |
| `/about/` | Feature list + keyboard tips |
| `/settings/` | Theme / wallpaper (localStorage) |
| `/export/training.csv` | Price history for offline analysis |

---

## For developers

**Read [`DEVELOPER.md`](DEVELOPER.md)** — file map, “I want to change…” table, request flow.

- Popular home games → `apps/games/constants.py`
- Data sources & keyshop warnings → [`SOURCES.md`](SOURCES.md)
- History of changes → [`CHANGELOG.md`](CHANGELOG.md) (newest first)

---

## Stack (actual)

| Layer | Choice |
|-------|--------|
| Backend | Django 5 |
| Prices | Steam public APIs, CheapShark, PSN JSON, polite BS4 search pages |
| Tasks | Optional Celery + Redis (`refresh_prices` works without) |
| UI | Django templates + Chart.js |

Philosophy: **public APIs first**, soft-fail scrapes, product data only (no seller PII).
