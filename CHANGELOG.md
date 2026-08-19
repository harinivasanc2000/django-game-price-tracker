# Changelog — full project log

Timestamps are approximate commit/session times (UTC/BST project work).

---

## 2026-08-19 21:10 BST — Graph seller dropdown + PSN / Amazon UK

### Added
- Graph **dropdown**:
  - **Average (all sellers)** — time-wise mean of available seller prices at each point (default)
  - **All sellers (overlay)** — every series on one chart
  - **Per seller** — Steam, Humble, Fanatical, etc. (whatever appears in deals/history)
- Launch reference still drawn as dashed baseline
- `apps/games/clients/external_stores.py`
  - Registers **PlayStation Store (UK)** and **Amazon UK** store rows
  - Deep-search links for PSN + Amazon UK (+ PS4/PS5 search hints)
- Detail page section **PlayStation & Amazon (UK)** with open-search links

### Honest limits
- **PSN** and **Amazon** have no free public bulk price API → links to official search, not live scraped prices
- Live auto-prices remain: Steam (region) + CheapShark PC stores
- Average can mix GBP/USD — disclaimer on the graph

### Still TODO
- [ ] Amazon Product Advertising API (needs keys) for live UK prices
- [ ] PSN product-id mapping for true digital prices
- [ ] CeX UK for used physical
- [ ] GBP FX normalisation on average chart
- [ ] Discord/email alerts

---

## 2026-08-19 20:45 BST — Celery + merged graph + this log

### Added
- `config/celery.py` — Celery app, daily beat at 06:00 Europe/London
- `config/__init__.py` loads `celery_app`
- `CELERY_BROKER_URL` / result backend (Redis default `redis://127.0.0.1:6379/0`)
- `apps/games/tasks.py` — refresh Steam + best third-party
- `python manage.py refresh_prices` (sync) / `--async` (Celery)
- Merged chart + keyshop disclaimers

### Note
- Celery needs Redis; without it use `refresh_prices` only

---

## 2026-08-19 20:35 BST — Seed slug fix + detail multi-store + stay-on-page track

### Fixed
- `UNIQUE constraint failed: games_game.slug` on `seed_launch_prices`

### Changed
- Title click = full detail without tracking
- Track/Untrack stay on detail page
- CheapShark multi-store deals

---

## 2026-08-19 20:20 BST — Clean home + popular

- No track/untrack flash on home
- Search → Tracked → Popular
- Superuser: prefer system Terminal if VS Code crashes on password

---

## 2026-08-19 19:55 BST — Comet wallpaper, drawer, login, launch prices

- SiteSettings, AdminChangeLog, launch_price seed, tracked drawer, login/profile, comet wallpaper

---

## 2026-08-19 19:40 BST — Search polish

- Typeahead, free vs unknown, aliases, DLC ranking, untrack

---

## 2026-08-19 earlier — Foundation

- Django project, Steam API, models, SOURCES, pilot → generic search

### Errors fixed earlier
- `no such table` → migrate first
- Hard-coded GoW → keyword search
- Track-on-click → view-first
- False Free → Unknown

---

## Commands

```bash
python manage.py migrate
python manage.py seed_launch_prices
python manage.py refresh_prices
python manage.py runserver
```
