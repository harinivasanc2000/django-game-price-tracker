# Changelog

**Rule:** Never overwrite past entries. Always **prepend** new sections at the top (newest first).

---

## 2026-08-20 21:02 BST — Fix FeatureNotFound: lxml missing

### Fixed
- `Couldn't find a tree builder with the features you requested: lxml` on `/steam/<id>/`
- `soup_from()` now uses **`html.parser`** (stdlib) when `lxml` is not installed
- Optional: `pip install lxml` still preferred for speed

```bash
git pull
# optional: pip install beautifulsoup4 lxml
python manage.py runserver
```

---

## 2026-08-20 20:35 BST — BeautifulSoup public product scrape + deal prediction

### Scraping policy
- **Public product search pages only** (title, price, public star/feedback %, product URL)
- **No** personal seller identity, addresses, phones, emails
- On 403/WAF/captcha → empty results + official search URL fallback
- Cached ~30 min; polite User-Agent

### Added
- `beautifulsoup4` + `lxml` in requirements
- `clients/scrape_utils.py` shared helpers
- CeX / eBay / GAME / Amazon UK parsers upgraded to BS4 where HTML is available
- **Deal outlook** heuristics (`prediction.py`)
- Template tag `{% deal_prediction_panel %}` + `_prediction.html`

### Install
```bash
pip install -r requirements.txt
git pull && python manage.py runserver
```

---

## 2026-08-20 20:05 BST — Appearance settings, tracked icons, hot-deal ghosts

### Added
- **Settings** nav (no login) → `/settings/`
- Themes + wallpapers (localStorage)
- Tracked drawer icons; translucent hot-deal covers

---

## 2026-08-20 19:55 BST — Changelog policy + full history restore

### Process
- CHANGELOG is **append-only** (prepend at top).

---

## 2026-08-20 19:50 BST — Clean home (deal-site style)

### Removed from home
- Recently viewed / Tracked list (drawer + History still)

### Added
- Popular grid with covers + live UK prices; hot strip vs launch

---

## 2026-08-20 19:10 BST — Search sort, export, share

### Added
- Search sort + hide DLC; export JSON; Copy/Share; savings badge

---

## 2026-08-20 18:25 BST — Nav, shortcuts, recently viewed

### Added
- Deals nav; `/` focus search; toast

---

## 2026-08-20 16:10 BST — Best tracked deals page

### Added
- `/deals/` sorted by lowest GBP

---

## 2026-08-20 16:00 BST — Disclaimer Continue fix

### Fixed
- Modal CSS `hidden` override

---

## 2026-08-20 15:55 BST — First-visit disclaimer + deal safety

### Added
- Disclaimer modal; safety tips; deal-filtered news

---

## 2026-08-20 15:50 BST — TemplateSyntaxError fix

### Fixed
- Django if parentheses in base.html

---

## 2026-08-20 15:45 BST — Detail layout: news sidebar, AJAX platforms, wallpaper

### Added
- Sidebar news; change-only chart; platform AJAX; game wallpaper

---

## 2026-08-20 15:15 BST — GBP FX, Watch, PriceAlert

### Added
- FX helpers; Watch + PriceAlert; profile alerts

---

## 2026-08-19 22:00 BST — Platforms, UK stores, news, social

### Added
- Platform filter; UK store links; Steam news; social links

---

## 2026-08-19 21:50 BST — PSN + Amazon public data

### Added
- PSN tumbler client; Amazon best-effort; offer chips

---

## 2026-08-19 21:10 BST — Chart seller dropdown + Average

### Added
- Per-seller + Average chart modes

---

## 2026-08-19 20:50 BST — Celery + multi-series chart

### Added
- Celery/Redis; sync `refresh_prices`; multi-series chart

---

## 2026-08-19 20:40 BST — Multi-store detail, track stays on page

### Added
- CheapShark deals; detail chart on view; seed slug fix

---

## 2026-08-19 20:20 BST — Extremely clean home (v1)

### Changed
- Minimal home layout

---

## 2026-08-19 19:55 BST — UI theme, drawer, admin settings, launch prices

### Added
- Comet wallpaper; tracked drawer; SiteSettings; seed launch prices

---

## 2026-08-19 19:45 BST — Search polish, free vs unknown, typeahead

### Added
- Typeahead; free/unknown/paid; untrack; search aliases

---

## 2026-08-19 18:15 BST — Browse history + compare chart baseline

### Added
- BrowseHistory; compare baseline

---

## 2026-08-19 (earlier session) — Core Django + Steam

### Scaffold
- Repo, models, Steam API, track snapshots, SOURCES warnings

### Errors fixed (early)
- migrations before seed; slug UNIQUE later fixed

---

## Backlog (not done / partial)

- [ ] Per-user track lists
- [ ] Discord / email alerts
- [ ] Stronger CeX when not blocked
- [ ] True historic MSRP via ITAD if licensed

---

## How to update this file

1. **Prepend** a new section at the top (below the Rule line).
2. List Added / Changed / Fixed / Removed.
3. Do **not** delete or rewrite older sections.
