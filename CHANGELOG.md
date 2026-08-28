# Changelog

**Rule:** Never overwrite past entries. Always **prepend** new sections at the top (newest first).

---

## 2026-08-28 — UK/BS4, advanced search, graphs, and full polish

### UK stores + BeautifulSoup
- Expanded automatic UK physical searches from 7 to **11 sources**: CeX, MusicMagpie, eBay UK, GAME, Argos, Currys, Smyths, The Game Collection, Hit, ShopTo, and SimplyGames; Amazon UK remains a separate best-effort source
- Wired every new specialist through the detail page, platform JSON API, AJAX platform switching, current-offer summary, cheapest-local ranking, and price graph
- Added a grouped **32-destination** all-platform directory covering official stores, PC retailers/comparison sites, UK shops, used sellers, marketplaces, and link-only social/classified searches
- Hardened public HTML fetching with thread-local pooled sessions, bounded responses/timeouts, block-page detection, gzip-safe headers, and soft-fail browser links
- Improved BS4 accuracy with recursive JSON-LD Product/ItemList parsing, direct product-link host allowlists, stock-aware deduplication, finite ratings/prices, and current-price detection that rejects years, RRP/“was” values, instalments, and foreign currency

### Search + filtering
- Added paid/free availability, verified minimum discount, new/used UK-link condition, full-games-only filtering, PS4/PS5 metadata filtering, and selectable 5/10/16 results per platform
- Added title-match, smart-value, price up/down, discount, cash-saving, and accent-insensitive name sorts across **all** platform buckets
- Smart value uses a relevance-dominant multi-objective score with discount/cash-saving evidence and logarithmic price dampening; unknown, NaN, and infinite prices always sort last
- Fixed max-price searches retaining unknown rows, descending price putting unknown rows first, invalid/reversed bounds, duplicate results, and control-character query joining
- Rebuilt remote autocomplete rows with DOM text nodes instead of `innerHTML`

### Graphs
- Replaced misaligned one-store-at-a-time averages with an event-aligned seller timeline, observed-point masks, fresh best/average series, and a seven-day last-known-quote expiry boundary
- Added seller/best/average/all-series controls, 30/90/365-day ranges, stepped lines, real-check dots/tooltips, responsive theme-aware rendering, and accessible summaries/status
- Normalised history and launch references to GBP, rejected non-finite values, kept free games, selected the cheapest same-store live quote, and restored graphs on non-Steam tracked pages
- Moved chart data to Django `json_script` so external store names cannot break into executable JavaScript

### Price correctness + performance
- Added one-query correlated SQL selection of the newest snapshot per `(game, store)` for home, deals, guide, and JSON export; old sales no longer beat current store prices
- Coalesce identical refresh snapshots for 20 hours while retaining changed offers and a daily heartbeat; invalid prices and out-of-range discounts are rejected/clamped before database writes
- Parallelised secondary tracked-price refreshes and public deal feeds with whole-batch deadlines; fixed executors that could wait after the page deadline
- Reused one BLAKE2-keyed raw platform search across filter/sort changes and moved the detail bundle to a short backend-safe `pb:v3` cache key
- Corrected launch-currency comparisons, free-price handling, out-of-stock/unknown-currency cards, admin cache invalidation/query loading, and direct tracked-deal links
- Expanded stored offer/alert URLs to 1,000 characters so long retailer redirects are not cut into broken links (migration `0006`)
- Tracked JSON export now includes every store's current offer while keeping the older singular `latest` field for compatibility

### Runability + documentation + tests
- Added `.env.example`; `run.sh` now installs dependencies only when missing, then migrates/seeds/serves as before
- Rewrote README/DEVELOPER maps with current UK coverage, request flows, algorithms, extension contracts, and verification commands
- Added regression coverage for search caching/ranking/filters, BS4 money/URL/JSON-LD parsing, graph alignment/expiry/XSS, current-price SQL, compact snapshots, specialist-store wiring, deal links, and exports

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
