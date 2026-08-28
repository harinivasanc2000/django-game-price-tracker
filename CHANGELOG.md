# Changelog

**Rule:** Never overwrite past entries. Always **prepend** new sections at the top (newest first).

---

## 2026-08-28 — Seasonal home ranking + appearance additions

### Home page
- Replaced the fixed “Popular” order with **Seasonal sale signals**: tracked discounted snapshots from the preceding 90 days, then current public Steam specials, then stable fallback titles
- The page explicitly labels this as sale activity rather than unverified unit-sales data
- Bumped and wired the home cache so tracking/untracking immediately refreshes the seasonal grid

### Appearance
- Added **Neon blue** and **Forest** themes
- Added **Sunset glow** and **Neon grid** static wallpapers

### Relevance + tests
- Normalise accented titles (for example, Ragnarök) before matching
- Prevent the 2018 God of War result from being confused with God of War Ragnarök
- Added regression coverage for the 90-day sale-signal ordering

---

## 2026-08-27 17:45 BST — Detail speed + presets + leaner UK

### Performance
- **`platform_bundle` cached 3 min** (`pb:v2`) — platform AJAX + reloads reuse data
- Detail pool timeout **9s**; UK physical pool **8s**; HTML fetches **6s**
- Single Game query on detail (active + launch in one hit)
- Skip Amazon scrape when condition=`used`
- Smaller per-store limits on focused platform views

### Search UX
- Quick presets: **Under £10 / £20 / £40**, Any price, Cheapest first

### Home
- Solid cards (already lean); keep disclaimer without heavy blur dependency in new CSS paths

```bash
git pull
python manage.py runserver
```

---

## 2026-08-25 14:35 BST — More improvements

### Relevance
- **PSN** over-fetch + `title_match` (less DLC / wrong-edition noise)
- **Xbox** same pattern + cache key bump
- **Amazon UK** BS4 over-fetch ×3 → title_match; used/renewed detection

### UX
- Console panel icons (PS / Xbox / Switch)
- Search page icons + lighter solid cards
- Click any **price** to copy (toast confirm) — include `_copy_price.js.html`
- Health: `GET /health/?stores=1` pings CeX API + Steam lightly

```bash
git pull
python manage.py runserver
```

---

## 2026-08-24 — Icons + BS4 policy + local stores

See prior entries / git log.

---

## Earlier

See git log.
