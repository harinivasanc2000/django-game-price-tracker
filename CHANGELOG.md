# Changelog — full project log

Timestamps are approximate commit/session times (UTC/BST project work).

---

## 2026-08-19 20:45 BST — Celery + merged graph + this log

### Added
- `config/celery.py` — Celery app, daily beat at 06:00 Europe/London
- `config/__init__.py` loads `celery_app`
- `CELERY_BROKER_URL` / result backend (Redis default `redis://127.0.0.1:6379/0`)
- `apps/games/tasks.py`
  - `refresh_one_game` — Steam + best CheapShark third-party snapshot
  - `refresh_all_tracked_prices` — all active tracked games
  - `refresh_single_game` — one game by id
  - Writes `AdminChangeLog` on full refresh
- `python manage.py refresh_prices` — sync refresh without Redis
- `python manage.py refresh_prices --async` — queue Celery
- Detail page **merged chart**: Steam (official) + third-party/keys + launch reference
- Disclaimers for keyshops / grey-market / currency mismatch

### How to run Celery
```bash
# Terminal 1 — Redis must be running
redis-server

# Terminal 2 — worker + beat
celery -A config worker -B -l info

# Or one-shot without Redis:
python manage.py refresh_prices
```

### Still TODO
- [ ] GBP conversion for CheapShark USD on chart
- [ ] Discord/email alerts on price drop
- [ ] Per-user watchlists
- [ ] CeX / Amazon / PSN UK
- [ ] AJAX track without reload

---

## 2026-08-19 20:35 BST — Seed slug fix + detail multi-store + stay-on-page track

### Fixed
- `IntegrityError: UNIQUE constraint failed: games_game.slug` in `seed_launch_prices`
  - Update by `steam_app_id`; unique slug fallback `title-pc-{appid}`

### Changed
- Title click shows full detail (Steam, launch, chart, stores) **without** tracking
- Track / Untrack stay on detail page (no compare redirect, no home banners)
- CheapShark multi-store deals on detail page

### Files
- `apps/games/clients/cheapshark.py` (new)
- `apps/games/management/commands/seed_launch_prices.py` (fixed)
- `apps/games/views.py`, `templates/games/steam_detail.html`

---

## 2026-08-19 20:20 BST — Clean home + popular

### Changed
- Home: no track/untrack flash messages
- Layout: Search → Tracked → Popular
- Popular list from seeded launch catalog

### Note
- VS Code can crash on `createsuperuser` password prompt — use system Terminal or:
  `python manage.py shell -c "...create_superuser..."`

---

## 2026-08-19 19:55 BST — Comet wallpaper, drawer, login, launch prices

### Added
- SiteSettings (wallpaper: comet / gradient / none)
- AdminChangeLog for admin/data audits
- Game.launch_price / launch_currency / launch_price_source / admin_notes
- `seed_launch_prices` with public UK/PC launch references
- Tracked side drawer (slide from right)
- Login / Profile nav (no default admin password)
- Lightweight comet rain canvas (~8 comets, ~30fps)

### Files
- `apps/games/models.py`, `admin.py`, `context_processors.py`
- `templates/base.html`, `templates/games/home.html`, `profile.html`, `registration/login.html`

---

## 2026-08-19 19:40 BST — Search polish (free vs unknown, typeahead)

### Added
- Netflix-style typeahead `/api/suggest/`
- `price_status`: paid | free | unknown (unknown ≠ free)
- Search aliases (GTA, cyberpunk, …)
- DLC ranking penalty
- Untrack

### Files
- `apps/games/clients/steam.py`, `views.py`, `templates/games/_search_box.html`

---

## 2026-08-19 earlier — Project foundation

### Added
- Private GitHub repo `django-game-price-tracker`
- Django apps: Game, Store, PriceRecord
- Steam public API search + appdetails
- Compare page + Chart.js
- README / SOURCES (official + grey-market warnings + UK physical)
- Pilot God of War / PS focus → expanded to generic Steam search
- run.sh one-command start

### Errors fixed along the way
- `no such table: games_store` → run makemigrations + migrate before seed
- Hard-coded God of War fetch → generic keyword search
- Track on title click → view-first, explicit Track
- False Free prices → Unknown when no overview

---

## Admin controls (ongoing)

| What | Where |
|------|--------|
| Wallpaper | Admin → Site settings |
| Launch MSRP | Admin → Games |
| Audit of admin/celery | Admin → Admin change logs |

---

## Commands cheat sheet

```bash
python manage.py migrate
python manage.py seed_launch_prices
python manage.py refresh_prices          # sync
python manage.py refresh_prices --async  # Celery
python manage.py createsuperuser
celery -A config worker -B -l info
python manage.py runserver
```
