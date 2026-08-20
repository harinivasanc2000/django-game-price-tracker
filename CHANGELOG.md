# Changelog

**Rule:** Never overwrite past entries. Always **prepend** new sections at the top (newest first).

---

## 2026-08-20 20:05 BST — Appearance settings, tracked icons, hot-deal ghosts

### Added
- **Settings** nav (no login) → `/settings/`
  - Themes: Dark red, Soft dark, Ember, Mist (dim light — not bright)
  - Wallpapers:
    - Live: Comet rain, Deep space (stars), Aurora
    - Static: Red haze, Night hills, Void, Deep ocean
    - Game art: Steam library art on detail pages
  - Saved in `localStorage` only (`gpt_theme`, `gpt_wallpaper`)
- **Tracked drawer**: capsule/cover icons beside each title
- **On sale vs launch**: very translucent cover image behind each chip

### Changed
- Staff admin link relabelled **Admin**; public **Settings** is appearance

---

## 2026-08-20 19:55 BST — Changelog policy + full history restore

### Process
- CHANGELOG is **append-only** (prepend at top).
- Restored entries that had been overwritten by short single-section updates.
- Timestamps aligned with git commits + project work sessions (BST).

---

## 2026-08-20 19:50 BST — Clean home (deal-site style)

### Removed from home main screen
- Recently viewed (still available under **History**)
- Tracked list (still in **Tracked** drawer + Profile / Deals)

### Added
- Hero search only on home
- **Popular grid**: Steam header images + live UK prices (parallel cached fetches)
- Discount pills + lowest GBP when multi-store snapshots exist
- **On sale vs launch** hot strip
- UI inspired by ITAD / GG.deals card grids

---

## 2026-08-20 19:10 BST — Search sort, export, share

### Search
- Sort: relevance / price ↑↓ / biggest discount / name
- **Hide likely DLC** toggle (default on)
- Cleaner result cards

### Deals / export
- `/export/tracked.json` — JSON export of tracked prices
- Link from Best deals page

### Detail
- **Copy link** + **Share** buttons
- **% under launch** savings badge
- `_detail_actions.html` partial

---

## 2026-08-20 18:25 BST — Nav, shortcuts, recently viewed (later removed from home)

### Added
- **Recently viewed** on home (session browse history) — *later removed from main home 19:50*
- Nav **Deals** → `/deals/`
- Press **`/`** to focus search
- Toast helper (`showToast`)
- Home quick links

---

## 2026-08-20 16:10 BST — Best tracked deals page

### Added
- `/deals/` — tracked games sorted by lowest GBP
- `% under launch` on deal rows
- `views_best_deals.py` helper

---

## 2026-08-20 16:00 BST — Disclaimer Continue fix

### Fixed
- First-visit modal **Continue** broken: CSS `display:flex` overrode HTML `hidden`
- Switched to class `.is-open`; Enter/Escape accept
- Cannot dismiss by clicking backdrop (must accept)

---

## 2026-08-20 15:55 BST — First-visit disclaimer + deal safety

### Added
- First-visit modal (blur + dialogue, `localStorage` key `gpt_disclaimer_v1`)
- Deal & safety tips on home
- Steam news filtered to sale / discount / free / price headlines
- Detail sidebar: deal news, stay-safe tips, ITAD/GG.deals-style links
- Best GBP pick tip under offer chips

---

## 2026-08-20 15:50 BST — TemplateSyntaxError fix

### Fixed
- `Could not parse the remainder: '(not' from '(not'` in `base.html`
- Django `{% if %}` does not allow parentheses — nested ifs without parens

---

## 2026-08-20 15:45 BST — Detail layout: news sidebar, AJAX platforms, wallpaper

### Added
- Wide layout; deals main column; **scrollable news sidebar**
- Graph shows **price-change points only** (flat stretches collapsed)
- Platform chips **without full page reload** (`/api/platform/<app_id>/`)
- Per-game **library_hero** wallpaper from Steam CDN
- Parallel fetch for deals + news + platform bundle

---

## 2026-08-20 15:15 BST — GBP FX, Watch, PriceAlert

### Added
- `fx.py` GBP conversion helpers
- Chart series in GBP
- **Watch** model + target price alerts
- **PriceAlert** model; admin registration
- Profile: watches, targets, clear alerts
- Watch form on detail when tracked + logged in

---

## 2026-08-19 22:00 BST — Platforms, UK stores, news, social

### Added
- Platform filter (PC / PS4 / PS5 / Xbox / Switch) on search
- UK local stores client (CeX, eBay, GAME, etc.) with polite fallbacks
- Steam news client + social/marketplace search links (X, Facebook Marketplace, etc.)
- Detail panels: UK physical, news, social chips

---

## 2026-08-19 21:50 BST — PSN + Amazon public data

### Added
- PSN UK Chihiro/tumbler public search client
- Amazon UK best-effort parser (often blocked → search-link fallback)
- Live offer chips (official / marketplace / third-party / used)
- Refresh task can snapshot PSN prices

---

## 2026-08-19 21:10 BST — Chart seller dropdown + Average

### Added
- Graph dropdown: per-seller (Steam, Humble, etc.) + **Average**
- PSN / Amazon sections on detail
- Multi-series Chart.js with launch baseline

---

## 2026-08-19 20:50 BST — Celery + multi-series chart

### Added
- Celery app + Redis broker settings
- Daily `refresh_prices` schedule; `refresh_single_game` task
- Sync fallback: `python manage.py refresh_prices` (no Redis required)
- Merged Steam + third-party chart series + keyshop disclaimer

### Known issue (user env)
- Redis connection refused if Redis not running — use sync command or `brew services start redis`

---

## 2026-08-19 20:40 BST — Multi-store detail, track stays on page

### Added / changed
- CheapShark public API multi-store PC deals
- Detail shows multi-store + chart **on title click** (not only after track)
- Track / untrack stay on detail page (toggle)
- Fix seed `UNIQUE` on `games_game.slug` (steam_app_id lookup + unique slug)

---

## 2026-08-19 20:20 BST — Extremely clean home (v1)

### Changed
- Home: search + tracked strip + popular text list
- No flash messages for track/untrack on home

---

## 2026-08-19 19:55 BST — UI theme, drawer, admin settings, launch prices

### Added
- Dark red/black theme; low-resource **comet rain** canvas wallpaper
- Right-side **Tracked** drawer
- Login / Profile nav (admin under staff Settings)
- `SiteSettings` (wallpaper, title, footer) + `AdminChangeLog`
- `launch_price` / currency / source on Game
- `seed_launch_prices` management command (public reference MSRPs)
- Profile page + logout form

---

## 2026-08-19 19:45 BST — Search polish, free vs unknown, typeahead

### Added / fixed
- Netflix-style search box + live suggestions API
- Price status: **free / unknown / paid** (unknown ≠ free)
- Untrack route; DLC hints; multi-word search scoring
- Aliases (GTA, CP2077, GoW, etc.)

---

## 2026-08-19 18:15 BST — Browse history + compare chart baseline

### Added
- `BrowseHistory` model + admin
- Session search/view/track history page
- Compare page: retail baseline, strikethrough original

---

## 2026-08-19 (earlier session) — Core Django + Steam

### Scaffold
- Private GitHub repo `django-game-price-tracker`
- Django apps, models: Game, Store, PriceRecord
- Steam store search + appdetails public API (no key)
- Generic keyword search (not God-of-War-only)
- Track Steam titles; price snapshots
- README / SOURCES.md: public APIs preferred; keyshop warnings; UK physical notes

### Errors fixed (early)
- `no such table: games_store` → run migrations before seed
- Seed IntegrityError slug UNIQUE → fixed later with app_id-first seed

---

## Backlog (not done / partial)

- [ ] Per-user track lists (not global `is_active`)
- [ ] Discord / email / webhook alerts
- [ ] Stronger CeX when not blocked
- [ ] True historic MSRP via ITAD (or similar) if licensed
- [ ] Sticky mobile action bar

---

## How to update this file

1. **Prepend** a new `## YYYY-MM-DD HH:MM BST — Title` section at the top (below the Rule line).
2. List Added / Changed / Fixed / Removed with bullets.
3. Do **not** delete or rewrite older sections.
