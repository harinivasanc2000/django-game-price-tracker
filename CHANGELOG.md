# Changelog — full project log

---

## 2026-08-19 21:50 BST — Public search scrape + UI

### Added
- **PSN UK live prices** via public Chihiro tumbler search JSON
  - `apps/games/clients/psn.py`
  - Full-game ranking, product links, platforms
- **Amazon UK** best-effort public search HTML parser
  - `apps/games/clients/amazon_uk.py`
  - When Amazon WAF blocks (common): shows search link, not fake prices
- Detail **live offer chips** (Steam / PSN / Amazon / best PC deal) sorted lowest first
- Refresh task also snapshots **PSN** (+ Amazon when unblocked)
- Chart includes PSN + Amazon points when available

### UI
- Offer chip grid with official / marketplace / third-party tags
- Clearer panels for PSN, Amazon, PC keystores

### Limits
- Amazon often returns captcha to servers/datacenters — browser search link fallback
- Keyshop deals still via CheapShark (USD)
- Be polite: no high-frequency scraping

### Still TODO
- [ ] CeX when endpoint allows
- [ ] GBP FX for USD deals on average chart
- [ ] Discord/email alerts
- [ ] Per-user watchlists

---

## 2026-08-19 21:10 BST — Graph seller dropdown + PSN/Amazon links

- Dropdown: Average / All / per-seller
- PSN + Amazon deep-search links (before live scrape)

---

## 2026-08-19 20:45 BST — Celery

- Daily refresh, `refresh_prices` command, Redis optional

---

## 2026-08-19 20:35 BST — Seed slug fix + multi-store detail

- Fixed UNIQUE slug on seed
- Track stays on page; CheapShark deals

---

## Earlier today

- Clean home, popular, typeahead, free vs unknown, comet wallpaper, launch prices, drawer, login

### Errors fixed
- Redis connection refused → use `refresh_prices` or start Redis
- Seed slug IntegrityError
- no such table → migrate first
- False Free → Unknown

---

## Commands

```bash
git pull
python manage.py runserver
python manage.py refresh_prices   # Steam + PSN + CheapShark (+ Amazon if allowed)
```
