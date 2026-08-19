# Changelog — full project log

---

## 2026-08-19 22:00 BST — Platforms, UK stores, news & social

### Added
- **Platform selector** (All / PC / PS4 / PS5 / Xbox / Switch) on search + detail chips
  - Adjusts PSN / Amazon / CeX / eBay query hints
- `apps/games/clients/uk_stores.py`
  - CeX + eBay UK best-effort public parse
  - Always-on search links: **CeX, GAME, Argos, Smyths, eBay UK, Facebook Marketplace, X, Reddit**
- `apps/games/clients/news.py`
  - **Steam public news API** per app
  - Social link-outs: X deals search, Reddit GameDeals/PS5, Facebook posts search
- Detail sections: UK physical/local, news, social

### Policy / limits
- **Facebook Marketplace**: link-only (login wall; we do not scrape accounts or marketplace data)
- **X/Twitter**: official search links for deal chatter (not scraped prices)
- CeX/eBay/GAME often **403 from servers** — works better from home IP or via browser links

### Still TODO
- [ ] GBP FX for mixed-currency average
- [ ] Price-drop alerts
- [ ] Per-user watchlists
- [ ] CeX when API allows authenticated partners

---

## 2026-08-19 21:50 BST — PSN live + Amazon best-effort + offer chips

- PSN Chihiro tumbler live GBP prices
- Amazon HTML when not WAF-blocked
- Live offer chip strip

---

## 2026-08-19 21:10 BST — Graph dropdown

- Average / All / per-seller chart filter

---

## 2026-08-19 20:45 BST — Celery

- `refresh_prices`, optional Redis worker

---

## Earlier

- Seed slug fix, clean home, typeahead, launch prices, wallpaper, track-on-page

```bash
git pull && python manage.py runserver
```
