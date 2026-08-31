# Django Game Price Tracker

A UK-first Django app for finding public game prices, comparing stores, viewing price history, and tracking drops. It covers PC, PS4, PS5, Xbox, Switch, UK physical retailers, used-game shops, and clearly labelled marketplace/keyshop links.

This is a comparison tool, not a store. Prices can change or be blocked by a retailer, so confirm the edition, platform, region, condition, delivery cost, and final price on the seller's page.

## Quick start

```bash
git clone https://github.com/harinivasanc2000/django-game-price-tracker.git
cd django-game-price-tracker
chmod +x run.sh
./run.sh
```

`run.sh` creates `.venv` when needed, installs missing dependencies, applies migrations, seeds optional reference prices, and starts Django. Open <http://127.0.0.1:8000/>.

For manual setup:

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py test
python manage.py runserver
```

Copy `.env.example` to `.env` if you want local overrides. Redis/Celery is optional; `python manage.py refresh_prices` records a compact cross-platform snapshot without it. To run the automatic 12-hour schedule, start a Redis server and a worker/beat process:

```bash
celery -A config worker --beat --loglevel=INFO --concurrency=2
```

## Main pages

| URL | Purpose |
|---|---|
| `/` | 90-day sale signals, current Steam specials, and stable fallbacks |
| `/search/` | Cross-platform results plus 32 encoded UK/direct store links |
| `/steam/<app_id>/` | Live multi-store comparison, filters, graph, and tracking |
| `/guide/` | Public deal feeds and buying guidance |
| `/deals/` | Lowest current tracked offers plus public deals |
| `/history/` | Recent searches, views, and tracking actions |
| `/research/` | Offline-analysis notes and training-data export |
| `/settings/` | Themes and wallpapers stored in the browser |
| `/export/tracked.json` | Current per-store offers for tracked games |
| `/export/training.csv` | Historical price snapshots for offline analysis |
| `/health/` | Database/cache health (`?stores=1` adds shallow store checks) |

## Search and UK coverage

Search supports:

- All platforms, PC, PS4, PS5, Xbox, or Switch.
- Minimum/maximum GBP, paid/free availability, minimum verified discount, and new/used UK-link condition.
- Steam/PSN full-games filtering, PS4/PS5 metadata checks, and 5/10/16 results per platform.
- Relevance, strict title match, smart value, price, discount, cash saving, and name sorting.
- Quick presets for free games, common price ceilings, 25%+ discounts, and cheapest first.

The 11-source UK bundle uses CeX's unofficial JSON endpoint first with a public BS4 fallback; MusicMagpie, eBay UK, GAME, Argos, Currys, Smyths, The Game Collection, Hit, ShopTo, and SimplyGames use public HTML. Amazon UK is attempted separately. Every source soft-fails to a clickable search link when a site blocks automated access.

The all-platform directory currently exposes 32 encoded destinations: official platform stores, authorised PC sellers, comparison services, UK retail, used shops, marketplaces, and social/classified fallbacks. Facebook Marketplace, Gumtree, Vinted, and similar services are link-only; the app does not log in or collect seller personal information.

## Techniques used

- **Strict title matching:** Unicode/accent normalisation, whole-word coverage, mandatory numeric/Roman sequel markers, subtitle discriminators, and contaminant rejection prevent accessories, DLC, and nearby franchise entries from being treated as the requested game.
- **Smart-value ranking:** `160 × title match + 0.35 × discount + 0.12 × capped cash saving − 2 × ln(1 + price)`. Relevance deliberately dominates a suspiciously cheap loose match; unknown/NaN/infinite prices sort last.
- **Reusable raw search cache:** canonical NFKC queries and fixed-length BLAKE2 keys let price/filter/sort changes reuse one four-platform result bundle; single-flight locks collapse simultaneous misses into one producer.
- **Defensive BS4 parsing:** bounded thread-local sessions, JSON-LD traversal, current-price detection, GBP/finite-number validation, host-allowlisted URLs, stock-aware deduplication, and card fallbacks.
- **Current-offer SQL:** correlated subqueries select the newest row for every `(game, store)` pair in one query, avoiding N+1 lookups; quotes expire from current-deal surfaces after seven days without a confirmed check.
- **All-store compact history:** one refresh stores the best validated Steam, PSN, Xbox, Nintendo, Amazon, UK-retailer, and bounded per-retailer CheapShark offer. Price/stock/URL/condition changes are immediate; unchanged rows get one 72-hour freshness checkpoint.
- **Aligned graph algorithm:** independently sampled sellers share a real-time-spaced event timeline; quotes carry forward for at most seven days, observed checks remain marked, and fresh best/average lines are calculated in GBP.
- **Hard concurrency budget:** three process-wide pools cap page, bundle, and UK work at 17 lazy threads by default. Deadlines cancel queued work, while one blocked retailer soft-fails without multiplying threads per request.

## Low-resource deployment

SQLite stays the zero-service default and uses WAL, normal synchronisation, persistent connections, and immediate write transactions. The local cache is capped at 800 entries. For multiple web workers, set `DATABASE_URL` to PostgreSQL and `CACHE_BACKEND`/`CACHE_LOCATION` to Django's Redis cache; the required drivers are already in `requirements.txt`. Worker and cache limits are documented in `.env.example` and can be lowered on a small machine.

## Data-source policy

Public APIs are preferred. BS4 clients read public product-search fields only and use caching, short limits, and graceful fallbacks. Keyshops and open marketplaces are risk-labelled; no price is a guarantee or endorsement. See [SOURCES.md](SOURCES.md).

## Developer documentation

Read [DEVELOPER.md](DEVELOPER.md) for the file map, request flows, extension contracts, and test commands. See [CHANGELOG.md](CHANGELOG.md) for newest-first implementation notes.

Stack: Django 5.1+, SQLite or PostgreSQL, requests, BeautifulSoup/lxml, optional Celery/Redis, Django templates, and Chart.js.
