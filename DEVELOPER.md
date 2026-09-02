# Developer map — read this before changing code

This guide maps the main request paths and explains the less-obvious algorithms. External retailers change often, so keep every client bounded, cached, and able to return an empty result with a usable browser link.

## Run and verify

```bash
./run.sh
```

Or run each step manually:

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
python manage.py runserver
```

`run.sh` only installs packages when imports are missing. Copy `.env.example` to `.env` for local overrides. Redis/Celery is optional for the web app.

`python manage.py refresh_prices` performs the same compact all-store refresh synchronously. With Redis, `celery -A config worker --beat --loglevel=INFO --concurrency=2` enables the default 12-hour schedule.

## Folder layout

```text
django-game-price-tracker/
├── manage.py
├── run.sh                     # create environment, migrate, seed, serve
├── config/                    # settings, root URLs, Celery setup
├── templates/
│   ├── base.html              # navigation, drawer, themes, wallpapers
│   └── games/
│       ├── steam_detail.html  # comparison page + atomic filtered navigation
│       ├── steam_search.html  # advanced cross-platform search/filter UI
│       └── _price_chart.html  # reusable safe Chart.js component
└── apps/games/
    ├── models.py              # Game, Store, PriceRecord, Watch, Alert, history
    ├── urls.py                # application routes
    ├── home_view.py           # 90-day sale-signal home ranking
    ├── search_view.py         # query validation and search-page context
    ├── platform_search.py     # parallel platform search, filters, raw cache
    ├── search_sort.py         # deterministic ranking and smart-value score
    ├── views_steam_detail.py  # live comparison orchestration
    ├── platform_bundle.py     # official + UK physical result bundle
    ├── views.py               # actions, history, autocomplete, graph payload
    ├── views_best_deals.py    # current tracked/public deals
    ├── buy_guide_view.py      # public recommendation feeds
    ├── views_export.py        # current-offer JSON + historical CSV
    ├── price_queries.py       # newest row per game/store in one SQL query
    ├── price_insights.py      # query-free daily-low/median deal summary
    ├── price_snapshots.py     # validation and unchanged-snapshot coalescing
    ├── cache.py               # safe keys, normal/empty-result TTLs
    ├── cache_keys.py          # shared UI cache identities
    ├── executors.py           # fixed process-wide external-I/O budgets
    ├── fx.py                  # currency to GBP
    ├── tasks.py               # refreshes and target-price email alerts
    ├── clients/
    │   ├── title_match.py     # strict cross-store title relevance
    │   ├── scrape_utils.py    # HTTP/BS4/JSON-LD/money/URL primitives
    │   ├── scrape_filters.py  # platform, condition, accessory, price filters
    │   ├── uk_stores.py       # 11-source UK bundle + direct links
    │   └── ...                # Steam, PSN, Xbox, Nintendo, CheapShark, Amazon
    ├── management/commands/   # seed and synchronous refresh commands
    └── tests/                 # network-free unit/regression tests
```

## “I want to change…”

| Goal | Main files |
|---|---|
| Seasonal home order | `home_view.py`; edit `constants.py` only for final fallback IDs |
| Search controls | `search_view.py`, `steam_search.html` |
| Search fetching/filtering | `platform_search.py` |
| Ranking formula | `search_sort.py` |
| Detail layout | `steam_detail.html` and its `_*.html` includes |
| Graph algorithm/UI | `views.py::_build_chart_payload`, `_price_chart.html` |
| Add a UK physical source | `clients/uk_stores.py`, then expose it through `platform_bundle.py` |
| Common BS4 parsing | `clients/scrape_utils.py` |
| Reject wrong products | `clients/title_match.py`, `clients/scrape_filters.py` |
| Steam/console clients | `clients/steam.py`, `psn.py`, `xbox.py`, `nintendo.py` |
| CheapShark/public feeds | `clients/cheapshark.py`, `public_deals.py` |
| Current-price card queries | `price_queries.py` |
| History-write policy | `price_snapshots.py` |
| Background refresh | `tasks.py`, `management/commands/refresh_prices.py` |
| Themes/wallpapers | `templates/base.html`, `templates/games/settings.html` |
| Database fields/indexes | `models.py`, then create and test a migration |
| Admin behaviour | `admin.py` |

## Request flows

### Search

1. `search_view.steam_search` canonicalises the query and validates every GET parameter.
2. `platform_search.multi_platform_search` checks a BLAKE2-keyed raw cache.
3. On a miss, Steam/PSN/Xbox/Nintendo run concurrently with a six-second batch deadline.
4. Strict title matching removes loose titles; Steam/PSN metadata removes DLC and wrong PlayStation generations.
5. Price/availability/discount filters and sorting run locally, so changing display filters reuses the raw bundle.
6. The template renders results plus grouped official, PC, and UK browser fallbacks.

### Detail page

1. `/steam/<app_id>/` loads the official Steam record and one optional tracked `Game` row.
2. CheapShark, news, similar titles, and `platform_bundle` run concurrently with a nine-second deadline.
3. `platform_bundle` concurrently requests platform APIs, Amazon, and the cached 11-store UK bundle (CeX API-first/BS4 fallback; other sources public HTML).
4. Each blocked source becomes an empty result plus `search_url`; it never crashes the page.
5. The page creates current offers and a safe JSON chart payload, then renders normal HTML.
6. Platform chips navigate to a fully recomputed filtered page, so top pick, chart, official panels, and local counts cannot become stale. `/api/platform/<app_id>/` remains available to JSON clients.

### Price refresh

1. `refresh_one_game` overlaps Steam with one cached all-platform/UK bundle and a bounded CheapShark lookup.
2. It selects one best finite offer per official/UK source and one per CheapShark retailer; explicit sold-out rows are stored as state and never alerted as deals.
3. `record_snapshot` validates prices/HTTP(S) links and coalesces unchanged rows for 72 hours. Every successful confirmation advances `last_checked_at`; price, URL, stock, condition, or discount changes are stored immediately.
4. All source writes use the same indexed `PriceRecord` history, including console-only tracked `Game` rows; no parallel history table is required.
5. Watches and existing alert keys are loaded once per game refresh, then trustworthy GBP targets create de-duplicated `PriceAlert` rows.
6. Run synchronously, queue through Celery, or use the default 12-hour Celery Beat entry.

## Algorithms and performance choices

### Title matching

`title_match.py` uses accent-insensitive normalisation, whole-word significant tokens, mandatory numeric/Roman sequel markers, query-token coverage, long-token subtitle discriminators, known sequel exclusions, and contaminant rejection. Do not weaken this to substring matching: that reintroduces accessories and franchise bleed.

### Smart-value search

The value score is:

```text
160 × match_score
+ 0.35 × discount_percent
+ 0.12 × min(cash_saving, 100)
- 2 × ln(1 + paid_price)
```

Title match has the dominant weight by design. All numeric inputs are finite-checked; missing prices sort last. Python's stable sort and accent-insensitive name keys make ties deterministic.

### Latest current offers

`PriceRecord` is append-only history. A current-price page must not use an arbitrary recent row. `latest_store_snapshots()` uses a correlated SQL subquery to return exactly one newest row per `(game, store)`, expires quotes after seven unconfirmed days, and uses `select_related` to prevent N+1 store/game queries. Current-offer views call `quote_needs_refresh()` to warn after 24 hours. Pass `max_age=None` only for archival/reporting code that explicitly wants stale latest rows.

`build_price_insights()` consumes the already-built bounded chart payload, groups real observed seller prices into one market low per local day, and returns display-only lowest-shown/median/confidence fields. Keep this calculation query-free and use “shown” or “sample” wording so sparse, capped, or blocked retailer coverage is not presented as a universal all-time low.

`export_game_prices_csv()` streams at most 5,000 rows with queryset iteration. Keep future per-game export fields scalar and spreadsheet-safe; do not materialise the full history in memory.

### Graph alignment

The graph accepts the newest 300 in-stock observations plus live quotes, converts finite non-negative values to GBP, and run-length-compacts flat prices while retaining freshness checkpoints. Sellers update asynchronously, so their last observed quote carries forward on a shared event timeline for at most seven days. The browser plots epoch values on a linear axis, so a six-month gap is wider than a one-minute gap. Observed masks distinguish real checks from carried values; best and average use fresh values only.

### BS4 safety and accuracy

`scrape_utils.py` supplies one pooled session per worker thread, bounded response size/time, block-page detection, GBP-aware price parsing, nested JSON-LD Product/ItemList traversal, finite rating/price validation, and HTTP(S) URL normalisation with optional retailer host allowlists. Prefer structured data, then narrowly scoped card selectors. Never collect seller PII or attempt login/captcha bypasses.

## Client contract

Clients return plain serialisable dictionaries/lists, not Django models. A priced product normally looks like:

```python
{
    "name": "Example Game PS5",
    "price": Decimal("29.99"),
    "currency": "GBP",
    "url": "https://retailer.example/product/example-game",
    "store_name": "Example Retailer",
    "in_stock": True,
    "condition": "new",
}
```

Scraper and Nintendo clients that expose blocked-state metadata return:

```python
{"results": [], "blocked": True, "search_url": "https://retailer.example/search?..."}
```

## Safe extension checklist

1. Put network code in `clients/`; use public pages/APIs and explicit timeouts.
2. Route repeated external calls through `cached()`.
3. Validate numbers, match titles, normalise direct links, and keep a browser fallback.
4. Add the result to `platform_bundle`, detail context/template, `tasks.py` source map, current offers, and graph if it contains prices.
5. Add fixture-based tests; tests must not depend on a retailer being online.
6. Run `check`, `makemigrations --check`, the full suite, and `git diff --check`.

## Cache invalidation

Shared UI keys live in `cache_keys.py`. Tracking and admin saves must invalidate the home-card and tracked-drawer keys. Bump a versioned network/bundle key whenever a cached payload shape changes.

`cache.cached()` uses backend-safe keys, short empty-result TTLs, and per-process single-flight locks. `executors.py` owns the only long-lived request I/O pools: page-level (6), platform-bundle (5), and UK stores (6). Do not introduce a per-request executor; tune the three `*_IO_WORKERS` variables instead. SQLite uses WAL/`BEGIN IMMEDIATE`; use `DATABASE_URL` + Redis cache for multiple web processes.

## Changelog rule

Always prepend new dated sections immediately below the opening rule in `CHANGELOG.md`. Never edit or delete older entries; they are the project reference history.
