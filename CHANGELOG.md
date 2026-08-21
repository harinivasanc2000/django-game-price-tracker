# Changelog

**Rule:** Never overwrite past entries. Always **prepend** new sections at the top (newest first).

---

## 2026-08-21 19:50 BST — Build on matching + deal links

### UK relevance (extends 19:05 title matching)
- Accessory reject list (controller, DualSense, headset, carry case, docks…)
- Matched UK rows **sorted by price ascending** so cheapest relevant listing is first
- Extra regression tests for accessories + sort order

### Deal / social links
- `social_news_links(title, platform=…)` — platform-aware Reddit links (PS5 / Xbox Game Pass / Switch Deals / Steam Deals)
- Still link-outs only; HotUKDeals + ITAD + GG.deals kept

```bash
git pull
python manage.py test apps.games.tests.test_uk_stores
python manage.py runserver
```

---

## 2026-08-21 19:05 BST — Graph quality + UK BS4 price matching

### Graphs
- Charts now render only when at least one real GBP data point exists (no blank “Now” graph)
- Added GBP axis labels, exact GBP hover tooltips, chronological interaction and clearer graph guidance

### UK local-store scrapers
- Kept the public-search **BeautifulSoup** approach for CeX, eBay UK, GAME, Argos, Currys and Smyths
- Added title-token matching before displaying rows, preventing unrelated controllers/accessories from being shown as game deals
- Local scraper bundle has its own 8-second deadline and preserves each store's clickable browser-search fallback on a timeout/error

### Latest deals
- Added a date-sorted HotUKDeals search link alongside Reddit, X, Steam news, ITAD and GG.deals
- Social/community sources remain link-outs only: no collection of personal seller information or brittle social scraping

### Tests
- Added graph-empty-state and UK result-relevance/fallback coverage

---

## 2026-08-21 18:45 BST — Deal links, graphs + CDKeys/Loaded resilience

### Store links
- **CDKeys now redirects to Loaded**: replaced the broken automated CDKeys scrape with a clearly labelled **Loaded (CDKeys)** browser-search fallback
- The fallback does not repeatedly hit the store's Cloudflare challenge; users can still open the live search in a normal browser
- CheapShark cards in Deals and Buy guide now open the **actual retailer redirect**, instead of silently opening the local comparison page
- Offer cards with no source URL are no longer fake `#` links

### Price and graph correctness
- Price graph internal points use ISO timestamps and are sorted chronologically before Chart.js renders them
- Multiple sellers' history can no longer be grouped by store order or overwrite same-minute points
- Home / Deals / JSON export use latest per-store/current snapshots; stale tracked offers show **Needs refresh** after seven days

### Reliability
- External-title cache keys are hashed when required so Memcached-compatible deployments accept spaces, Unicode and punctuation in game names
- Platform-search workers now return partial results at the timeout instead of waiting again on executor shutdown
- Steam detail and platform-store bundles now use shared 12s / 10s deadlines; slow or blocked scrapers return their normal search-link fallback instead of freezing the page
- Added regression coverage for graph order, Loaded fallback, current offers, exports, tracking and alerts

---

## 2026-08-21 18:35 BST — Performance polish + bug fixes

### Performance
- **Shared `requests.Session`** + connection pool in `scrape_utils` and Steam client
- **Home page cache** (3 min) + **single PriceRecord query**
- **Multi-platform search top-level cache** (3 min) with hard 8s parallel timeout
- Empty / blocked scrape results cached only **90s**
- Steam search aliases expanded; max 3 query expansions

### Bug fixes
- Cache keys include **limit**; Xbox `price=None` when unknown; history prune TZ fix; track/untrack cache bust; slimmed `views.py`

### Ops
- `/health/` reports DB + cache + tracked count

---

## 2026-08-21 17:55 BST — Official stores first + full UK local scrapes

- Official storefront first per platform; full UK scrapes including Smyths

---

## Earlier

See git log.
