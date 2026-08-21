# Developer map — read this before changing code

This project grew feature-by-feature. This file is the **map** so you can find
things quickly and change them safely.

---

## How to run (short)

```bash
cd django-game-price-tracker
source .venv/bin/activate   # or: python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_launch_prices   # optional launch MSRP data
python manage.py runserver
```

Optional one-liner: `./run.sh` (creates venv, migrates, seeds, serves).

---

## Folder layout

```
django-game-price-tracker/
├── manage.py                 # Django entry
├── requirements.txt
├── run.sh                    # local start helper
├── README.md                 # user-facing overview
├── DEVELOPER.md              # this file
├── CHANGELOG.md              # newest changes at the TOP — never overwrite
├── SOURCES.md                # stores / APIs / keyshop warnings
├── config/                   # Django project settings, urls, celery
├── templates/
│   ├── base.html             # nav, drawer, themes, wallpapers
│   └── games/                # page templates
└── apps/games/               # almost all app logic lives here
    ├── models.py             # Game, Store, PriceRecord, Watch, …
    ├── constants.py          # POPULAR_APP_IDS, platform lists
    ├── urls.py               # every URL route
    ├── views.py              # track/untrack, chart helper, platform bundle, profile
    ├── views_steam_detail.py # game detail page (main comparison UI)
    ├── home_view.py          # home page
    ├── search_view.py        # search results
    ├── buy_guide_view.py     # /guide/ public deals
    ├── research_view.py      # /research/ ML notes
    ├── about_view.py         # /about/ feature list
    ├── views_best_deals.py   # /deals/
    ├── views_export.py       # JSON + CSV export
    ├── fx.py                 # currency → GBP
    ├── cache.py              # simple timed cache for API calls
    ├── prediction.py         # buy-now heuristic (not real ML)
    ├── clients/              # external data (Steam, CheapShark, scrapers)
    ├── management/commands/  # seed_*, refresh_prices
    └── templatetags/         # {% deal_prediction_panel %} etc.
```

---

## "I want to change…"

| Goal | File(s) |
|------|--------|
| Home popular game list | `apps/games/constants.py` → `POPULAR_APP_IDS` |
| Nav links | `templates/base.html` |
| Themes / wallpapers JS | `templates/base.html` (bottom script) |
| Detail page layout | `templates/games/steam_detail.html` |
| Add a new URL | `apps/games/urls.py` + a small `*_view.py` |
| Steam API calls | `apps/games/clients/steam.py` |
| CheapShark / multi-store | `apps/games/clients/cheapshark.py`, `public_deals.py` |
| UK scrapes (CeX, eBay…) | `apps/games/clients/uk_stores.py`, `scrape_utils.py` |
| Digital store scrapes | `apps/games/clients/digital_stores_bs4.py` |
| GBP conversion | `apps/games/fx.py` |
| DB fields | `apps/games/models.py` then `makemigrations` / `migrate` |
| Daily price refresh | `apps/games/management/commands/refresh_prices.py`, `tasks.py` |
| Admin UI | `apps/games/admin.py` + `/admin/` |

---

## Request flow (detail page)

1. User opens `/steam/<app_id>/`
2. `views_steam_detail.steam_detail` loads Steam app details
3. Parallel threads fetch: CheapShark, news, UK stores, digital stores, similar titles
4. Template shows offers, chart, panels; scrapers soft-fail (page still works)

**Rule:** never let one blocked store crash the whole page — wrap external calls in `try/except`.

---

## Models (mental model)

- **Game** — a title you track (`steam_app_id`, `launch_price`, `is_active`)
- **Store** — Steam, CeX, Amazon, …
- **PriceRecord** — one price snapshot (history + CSV export)
- **Watch** — logged-in user + target price alert
- **BrowseHistory** — session search/view/track log
- **SiteSettings** — admin site title / footer (pk=1 singleton)

---

## Clients contract

Every client should return **plain dicts/lists**, not Django models.

Typical product row:

```python
{
  "name": "…",
  "price": Decimal("9.99"),   # or float after serialize
  "currency": "GBP",
  "url": "https://…",
  "store_name": "Steam",
}
```

Scrapers: product data only (no personal seller PII).

---

## Features already built

- Search + autocomplete (Steam)
- Detail multi-store compare (Steam, CheapShark, PSN, Amazon, UK, digital)
- Track / untrack + right drawer
- Launch price vs current + simple prediction panel
- Chart (change-only points, seller dropdown, average)
- Buy guide `/guide/` + public Steam specials
- Research lab + training CSV export
- Appearance settings (localStorage themes/wallpapers)
- Health endpoint `/health/`
- Celery tasks (optional; needs Redis)

---

## Safe ways to extend

1. **New store** — add function in `clients/`, call it from `_platform_bundle` or `fetch_digital_bundle`, soft-fail, show link if blocked.
2. **New page** — `my_view.py` + template + one line in `urls.py` + nav in `base.html`.
3. **New field on Game** — models → migrate → admin → template.
4. **Offline ML** — train outside Django; later load a JSON of scores if you want (do not train on the web server).

---

## Changelog rule

Always **prepend** new dated sections at the top of `CHANGELOG.md`. Never delete old entries.
