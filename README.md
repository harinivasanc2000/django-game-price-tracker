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

Copy `.env.example` to `.env` if you want local overrides. Redis/Celery is optional; `python manage.py refresh_prices` works without it.

## Main pages

| URL | Purpose |
|---|---|
| `/` | 90-day sale signals, current Steam specials, and stable fallbacks |
| `/search/` | Unified Steam, PSN, Xbox, Nintendo, and UK-store search |
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
- Full-games-only filtering, PS4/PS5 metadata checks, and 5/10/16 results per platform.
- Relevance, strict title match, smart value, price, discount, cash saving, and name sorting.
- Quick presets for free games, common price ceilings, 25%+ discounts, and cheapest first.

Automatic UK price extraction uses public product-search pages for CeX, MusicMagpie, eBay UK, GAME, Argos, Currys, Smyths, The Game Collection, Hit, ShopTo, and SimplyGames. Amazon UK is also attempted separately. Every source soft-fails to a clickable search link when a site blocks automated access.

The all-platform directory currently exposes 32 encoded destinations: official platform stores, authorised PC sellers, comparison services, UK retail, used shops, marketplaces, and social/classified fallbacks. Facebook Marketplace, Gumtree, Vinted, and similar services are link-only; the app does not log in or collect seller personal information.

## Techniques used

- **Strict title matching:** Unicode/accent normalisation, significant-token coverage, whole-word checks, subtitle discriminators, and contaminant rejection prevent accessories, DLC, and nearby franchise entries from being treated as the requested game.
- **Smart-value ranking:** `160 × title match + 0.35 × discount + 0.12 × capped cash saving − 2 × ln(1 + price)`. Relevance deliberately dominates a suspiciously cheap loose match; unknown/NaN/infinite prices sort last.
- **Reusable raw search cache:** canonical NFKC queries and fixed-length BLAKE2 keys let price/filter/sort changes reuse one four-platform result bundle instead of repeating network work.
- **Defensive BS4 parsing:** bounded thread-local sessions, JSON-LD traversal, current-price detection, GBP/finite-number validation, host-allowlisted URLs, stock-aware deduplication, and card fallbacks.
- **Current-offer SQL:** correlated subqueries select the newest row for every `(game, store)` pair in one query, avoiding N+1 lookups and expired-sale mistakes.
- **Compact history:** unchanged snapshots are coalesced for 20 hours while price/stock/condition changes and a daily heartbeat remain available.
- **Aligned graph algorithm:** independently sampled sellers share an event timeline; quotes carry forward for at most seven days, observed checks remain marked, and fresh best/average lines are calculated in GBP.
- **Bounded concurrency:** store calls run in small pools with whole-batch deadlines and soft failure, so one blocked retailer does not prevent the page rendering.

## Data-source policy

Public APIs are preferred. BS4 clients read public product-search fields only and use caching, short limits, and graceful fallbacks. Keyshops and open marketplaces are risk-labelled; no price is a guarantee or endorsement. See [SOURCES.md](SOURCES.md).

## Developer documentation

Read [DEVELOPER.md](DEVELOPER.md) for the file map, request flows, extension contracts, and test commands. See [CHANGELOG.md](CHANGELOG.md) for newest-first implementation notes.

Stack: Django 5, requests, BeautifulSoup/lxml, optional Celery/Redis, Django templates, and Chart.js.
