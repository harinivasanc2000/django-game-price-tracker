# Changelog

**Rule:** Never overwrite past entries. Always **prepend** new sections at the top (newest first).

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
- **Shared `requests.Session`** + connection pool in `scrape_utils` and Steam client (fewer TCP handshakes)
- **Home page cache** (3 min) + **single PriceRecord query** (no N+1 per popular card)
- **Multi-platform search top-level cache** (3 min) with hard 8s parallel timeout → partial results instead of hangs
- Empty / blocked scrape results cached only **90s** (retry sooner without hammering)
- Steam search aliases expanded (bg3, elden, tlou, spiderman…); max 3 query expansions

### Bug fixes
- Cache keys now include **limit** (PSN / Xbox / Nintendo / Steam) — no stale short lists
- Xbox rows use `price=None` when unknown (not `0`) so ranking stays honest
- History prune uses proper `datetime.fromisoformat` + aware TZ (was fragile)
- Track / untrack **busts** tracked drawer + home caches immediately
- `views.py` slimmed: dead duplicate home/search/detail paths removed; keep track/profile/history/suggest

### Ops
- `/health/` reports DB + cache + tracked count (503 if degraded)

```bash
git pull
python manage.py runserver
# curl http://127.0.0.1:8000/health/
```

---

## 2026-08-21 17:55 BST — Official stores first + full UK local scrapes

### Behaviour
- **PS4 / PS5:** PlayStation Store (UK) listed and ranked **first**, then local UK shops
- **Xbox:** Microsoft / Xbox Store **first**, then local
- **Switch:** Nintendo eShop **first**, then local
- **PC:** Steam first, then CheapShark / keyshops
- Offer chips sort: preferred official store → other official → price

### Local UK scraping (public product search only)
- **Full parallel scrapes:** CeX, eBay, GAME, Argos, Currys, **Smyths Toys** (new)
- Higher row limits (up to 10–12 on console filters)
- Always keep clickable search URLs when a site blocks bots
- No personal seller PII — title, price, public rating, product URL only

### UI
- Detail panels order: Official digital (PSN / Xbox / Nintendo) → UK physical → Amazon → PC third-party
- Platform chips show the matching official panel + physical for that platform
- Search page labels sections with **Official** badges

---

## 2026-08-21 07:35 BST — Code cleanup + About + free deals

### For you (readability)
- **`DEVELOPER.md`** — full map of folders, “I want to change…”, request flow
- **`apps/games/constants.py`** — `POPULAR_APP_IDS` + platform lists in one place
- **`urls.py`** — grouped + commented routes
- **README** rewritten to match the real stack
- **`run.sh`** updated (seed_launch_prices, useful URLs)

### Features
- **`/about/`** — pages, keyboard shortcuts, safety, dev pointers
- **Free / giveaway** section on `/guide/` (CheapShark `upperPrice=0`)
- Home imports popular IDs from `constants.py` (easier to edit)

---

## 2026-08-21 04:35 BST — Buy guide + public Steam / CheapShark feeds

- `/guide/`, Steam specials on home, multi-store deals on `/deals/`

---

## 2026-08-21 04:25 BST — Training CSV + detail digital panel

- `/export/training.csv`, digital store panel, similar games

---

## Earlier

See git log.
