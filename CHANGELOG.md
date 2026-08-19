# Changelog & status

Comment on each item: **done** / **needs work** / **skip for now**.

---

## Done

### Project foundation
- [x] Private GitHub repo `django-game-price-tracker`
- [x] Django project skeleton (`config/`, `apps/games/`, SQLite)
- [x] Models: `Game`, `Store`, `PriceRecord` (physical/used flags, currency, discount)
- [x] Django admin for all models
- [x] `SOURCES.md` — official APIs, aggregators, UK physical (CeX, Amazon, GAME), grey-market list with warnings
- [x] `run.sh` one-command local start
- [x] UK defaults (GBP, GB, Europe/London)

### UI
- [x] Dark theme base template
- [x] Home page with tracked games list
- [x] Platform filter chips (PS4 / PS5 / PC / Xbox / Switch / All)
- [x] Comparison page (offers, badges: physical / digital / used / lowest)
- [x] **Search bar** → Steam store search (any keyword)
- [x] Steam results with **thumbnails**, price, platforms, editions
- [x] **Track & save price** from search → creates Game + PriceRecord + opens compare page
- [x] Nav: Tracked | Search Steam | Admin

### Steam (generic, not God-of-War-only)
- [x] `search_store(term)` via `/api/storesearch/`
- [x] `get_app_price(app_id)` via `/api/appdetails`
- [x] Country code support (`cc=GB` default)
- [x] Cover/header image stored on Game when tracking
- [x] Legacy commands still exist: `fetch_steam_gow`, `seed_pilot` (optional)

### Price history (limited by Steam)
- [x] Chart.js line chart on compare page
- [x] Price change vs previous snapshot (↑/↓ %)
- [x] Each **Track** or re-fetch adds a new `PriceRecord` (builds history over time)
- [ ] **Not available from Steam public API:** full historical lows / calendar history  
  → Needs repeated daily fetches (Celery later) **or** ITAD / GG.deals APIs

### CeX / physical (prepared, not primary)
- [x] Polite CeX client + `fetch_cex_gow` command (unofficial API)
- [ ] Wire CeX into UI search (after Steam is solid)
- [ ] Amazon UK / GAME / PSN digital

---

## Not done yet (backlog)

- [ ] Daily automated price checks (Celery + Redis)
- [ ] Email / Discord / Telegram alerts on price drop
- [ ] User accounts + personal watchlists
- [ ] GG.deals / IsThereAnyDeal integration (multi-store + true history)
- [ ] PlayStation Store digital prices
- [ ] CeX search from UI (not only GoW command)
- [ ] Amazon UK prices
- [ ] Keyshop prices via aggregators only (with risk labels)
- [ ] Deduplicate offers better (same store, keep latest only in list — partially done)
- [ ] Pagination on Steam search
- [ ] Mobile polish

---

## How history works today

Steam only returns **current** price.  
Our graph = snapshots **you** saved (each time you click Track, or run a fetch command).

To build history for a game:
1. Search → Track once
2. Later: open Search, find same game, Track again (or we add a “Refresh price” button next)

True multi-year history → ITAD / GG.deals / SteamDB-style sources later.

---

## Quick test after pull

```bash
git pull
python manage.py runserver
```

1. http://127.0.0.1:8000/ — search bar  
2. Search `Assassin's Creed` → many titles + thumbnails  
3. Search `Assassin's Creed Brotherhood` → narrower list  
4. Click **Track & save price** → compare page + chart grows with more snapshots  
