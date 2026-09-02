# Changelog

**Rule:** Never overwrite past entries. Always **prepend** new sections at the top (newest first).

---

## 2026-09-02 — Dynamic platform home feeds and motion polish

- Made the home platform selector update the page in place: PS4, PS5, Xbox, and Switch now render their own UK deals and discounts, while `?platform=` remains a server-rendered progressive fallback and `/api/home-deals/` serves the same escaped HTML fragment
- Added bounded BeautifulSoup home-feed providers for PSNDeal GB (PS4/PS5), the official Xbox UK sales page, and NTPrices (Switch); numeric deal fields are finite-checked, links/images are host-allowlisted, and cards are de-duplicated, capped, and clearly attributed
- Kept platform changes low-resource with one compact cached payload per provider family, shared PlayStation fetching, single-flight cache production, separate three-minute home keys, fresh local snapshot merging, and official browse links whenever a public page is empty, changed, slow, or blocked
- Isolated background refreshes by catalogue platform: console games no longer run Steam/CheapShark work, PC games no longer store console offers, and PlayStation bundle rows respect PS4/PS5 generation metadata
- Added a responsive sticky search surface, lazy images, mobile horizontal snap cards, scroll progress, and viewport reveal transitions using passive/requestAnimationFrame work; reduced-motion visitors get immediate static content and animated wallpapers stop as their system preference changes
- Added offline parser, platform-isolation, progressive-rendering, fragment-escaping, cache, and motion-accessibility regressions

---

## 2026-09-02 — Price insights, smarter watches, and focused exports

- Added a zero-query price-insight panel that reuses graph data to show the current best, 30-day low, daily recorded median, deal verdict, and evidence confidence without claiming a market-wide all-time low; the deal outlook now reuses the same summary instead of issuing a second history query
- Upgraded the profile watchlist with each game's cheapest fresh offer, target gap/reached state, and inline target editing; verified free offers now appear on current-deal surfaces and can trigger a £0 target alert
- Added a bounded streaming CSV export for each active game's history with constant-memory iteration and spreadsheet-formula protection
- Added a 24-hour “Needs refresh” warning with semantic check times while retaining the seven-day hard expiry for unconfirmed current offers
- Added `last_checked_at` to compact snapshots: unchanged refreshes update one timestamp in place, preserving the original graph event while preventing fresh confirmations from looking stale
- Added offline regression coverage for daily insight sampling, stale/free prices, watch updates, quote warnings, and isolated per-game exports

---

## 2026-08-31 — Small reliability follow-up

- Prevented busy shared worker pools from caching partial search, bundle, or home results for the normal full lifetime
- Fixed optional PostgreSQL URL parsing and kept Celery Beat on the environment-controlled refresh schedule
- Expired unconfirmed seven-day-old quotes from current-deal surfaces while preserving their historical records

---

## 2026-08-30 — Cross-platform history, fixed resource ceilings, and correctness pass

### Compact all-platform price history
- Rebuilt the refresh worker around the existing indexed `PriceRecord` stream: Steam, PlayStation, Xbox, Nintendo, Amazon, all 11 UK sources (including four specialist shops), and up to six distinct CheapShark retailers now store comparable per-store history
- Added console/manual game refreshes without requiring a Steam app id; a single cached all-platform bundle supplies official and local prices, while one best finite offer per source prevents duplicate search-result rows
- Store price, URL, discount, condition, and stock changes immediately; unchanged quotes now create one 72-hour freshness checkpoint instead of daily rows, remaining inside the graph's seven-day quote lifetime
- Persist explicit sold-out transitions so current-deal queries cannot fall back to an older in-stock sale; sold-out/unknown offers never trigger target-price alerts and unsafe links are stripped before storage
- Serialised each game's compare/create sequence with an atomic parent-row lock and SQLite immediate transactions; watches and existing alert keys are preloaded once per refresh
- Replaced the fixed daily Beat entry with an environment-controlled 12-hour schedule, bounded worker/prefetch/result settings, synchronous `refresh_prices` support, optional PostgreSQL `DATABASE_URL`, and Redis cache configuration examples

### Low-resource / fast-result architecture
- Replaced nested per-request executors with three lazy process-wide pools: 6 page I/O workers, 5 platform-bundle workers, and 6 UK-store workers; limits are environment-tunable and timed-out queued work is cancelled
- Added per-key single-flight cache production so simultaneous home/search/store misses share one external request instead of stampeding retailers; idle lock entries are removed automatically
- Cached legitimate `None`/not-found responses with the short negative-result TTL, eliminating repeated Steam misses, and removed a redundant second platform-bundle cache write
- Bounded the local memory cache at 800 entries, retained short blocked-result TTLs, and enabled SQLite WAL, normal synchronisation, persistent connections, and `BEGIN IMMEDIATE` writes
- Reduced home cold-start fan-out, reused bundle/client caches across pages and background refreshes, and kept Redis/PostgreSQL optional so the default local install remains zero-service
- Raised the supported Django floor to 5.1 for the SQLite transaction settings and consolidated Beat configuration so the environment-controlled 12-hour sweep cannot be overwritten during Celery startup

### Deals, filters, graphs, and safety
- Required numeric and Roman-numeral title markers, fixing RDR 2, Resident Evil 4, Football Manager 2024, Cyberpunk 2077, and Final Fantasy VII matching their base/other entries
- Fixed reversed platform price bounds, invalid conditions/platforms/countries, bounded numeric inputs, unknown/free rows outside an active band, and persistent non-HTTP retailer/news URLs
- Removed explicitly sold-out rows from top picks, alerts, current comparison offers, and best/average chart series; non-Steam compare pages now select each store's newest in-stock row instead of its historical cheapest sale
- Expired unconfirmed quotes from current deal cards, comparisons, and exports after seven days while retaining the full append-only history for charts and offline analysis
- Preserved periodic confirmations during flat-price graph compaction and changed Chart.js to real elapsed-time spacing on a linear epoch axis; seller colours remain valid beyond 12 series
- Replaced partial platform AJAX updates with cached full filtered navigation so official panels, links, source counts, top pick, and graph update atomically
- Made autocomplete abort/version stale requests, reset keyboard state, refresh platform links, and expose combobox/listbox semantics; added tracked-drawer modal focus management

### Documentation and regression coverage
- Corrected UK source/API descriptions, Steam/PSN-only full-game filtering, CeX API-first behavior, current environment variables, and platform navigation documentation
- Added deterministic regressions for cross-platform history/coalescing/stock changes, cache single-flight, sequel matching, latest current offers, graph freshness/time data, malformed filters, unsafe links, autocomplete races, and drawer accessibility

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
