# 🎮 Data Sources & Public APIs

This file documents **all legitimate stores, aggregators, public APIs, domains and newsletters** we plan to support, plus third-party keyshops and **UK physical resellers**.

**Current focus**: United Kingdom across PC, PS4, PS5, Xbox, Switch, and physical/used game retailers.

**Philosophy**: Prefer official / public APIs + reputable aggregators. Be extremely careful with any internal/unofficial endpoints (e.g. CeX). Store secrets in environment variables only.

## Current implemented coverage (2026-09-02)

- **Official/platform results:** Steam, PlayStation Store UK, Xbox/Microsoft Store UK, and Nintendo eShop UK.
- **Aggregated PC deals:** CheapShark, with keyshop/marketplace risk labels.
- **Dynamic console home deals:** PSNDeal GB for PS4/PS5, the official Xbox UK sales page, and NTPrices for Switch, merged with fresh locally tracked offers.
- **Automatic UK product search:** CeX (unofficial JSON endpoint first, public BS4 fallback), plus public HTML for MusicMagpie, eBay UK, GAME, Argos, Currys, Smyths, The Game Collection, Hit, ShopTo, and SimplyGames. Amazon UK is a separate best-effort public-page client.
- **Browser fallbacks:** all automatic sources plus official stores, Humble, Fanatical, Green Man Gaming, GOG, Epic, Loaded/CDKeys, Eneba, GG.deals, IsThereAnyDeal, AllKeyShop, Cash Converters, Facebook Marketplace, Gumtree, Vinted, and PriceRunner.
- **Social/classified policy:** link-only; no login, seller-profile collection, or personal seller data.

Retail HTML can change or be blocked at any time. Empty automated results therefore retain an encoded public search link.

---

## 1. Official Platforms (Best & Safest)

### Steam
- **Website**: https://store.steampowered.com
- **Public Store API** (no key required for basic prices):
  ```
  GET https://store.steampowered.com/api/appdetails?appids={APP_ID}&cc={COUNTRY_CODE}&filters=price_overview
  ```
- **Rate limit**: ~200 requests / 5 minutes
- **Notes**: Best starting point for PC. Returns `price_overview` with final/initial price in cents + discount %.
- **Credentials:** none used for Store API pricing.

### PlayStation Store (PSN)
- **Website**: https://store.playstation.com/en-gb/
- **Access**: The app uses the public Chihiro storefront search endpoint; it is not a guaranteed/stable official developer API.
- **Notes**: Primary digital source for PS4/PS5. Region = GB for UK.
- **Status**: Implemented with strict title/full-game metadata filtering and direct Store links.

### Xbox / Microsoft Store UK
- **Website**: https://www.xbox.com/en-gb/
- **Home sale page**: https://www.xbox.com/en-gb/promotions/sales/sales-and-specials
- **Status**: The official public sale page supplies Xbox home cards; only finite GBP game offers with Xbox-hosted links are retained.

### Nintendo eShop UK
- **Website**: https://www.nintendo.com/en-gb/
- **Status**: Official browser/search links remain the purchase destination. The dynamic home summary uses the independent NTPrices tracker described below because Nintendo does not provide this project with a stable public sale API.

### Epic Games Store
- **Website**: https://store.epicgames.com
- **Status**: Planned – use carefully / via aggregators.

### Ubisoft / Rockstar
- Better via aggregators for now.

---

## 2. Price Aggregators (Highly Recommended)

### GG.deals
- **Website**: https://gg.deals
- **API**: https://gg.deals/api/
- **Status**: Browser fallback only; no API credential is read by the app.

### IsThereAnyDeal (ITAD)
- **Website**: https://isthereanydeal.com
- **Docs**: https://docs.isthereanydeal.com
- **Status**: Browser fallback only; no API credential is read by the app.

### Other
- **CheapShark: implemented** for aggregated PC offers.
- **PSNDeal: implemented** as a public HTML price-tracker feed for PS4/PS5 home cards: https://psndeal.com/gb
- **NTPrices: implemented** as a public HTML price-tracker feed for Switch home cards: https://ntprices.com/
- PSNDeal and NTPrices are independent aggregators, not Sony/Nintendo stores; their cards link to price-history pages and the UI separately retains official storefront browse links.
- PSprices, other PlatPrices properties, and Hot.Game remain possible future sources.

The three console home providers are parsed with bounded BeautifulSoup selectors. Results are restricted to finite GBP sale/current values, source-host-allowlisted product and image URLs, stable title de-duplication, and 12 cards. One compact payload is cached per provider family for 15 minutes (PS4/PS5 share it), while blocked/empty results use a shorter retry cache and soft-fail to official browse links.

---

## 3. UK Physical Resellers (New Focus)

The implemented bundle covers **physical discs/cartridges** across the UK platforms.

### CeX (uk.webuy.com)
- **Website**: https://uk.webuy.com
- **Type**: Second-hand + some new. Excellent for cheap used PS4/PS5 games.
- **Internal API** (community reverse-engineered):
  - Base: `https://wss2.cex.uk.webuy.io/v3/`
  - Search example: `/boxes?q=God+of+War&firstRecord=1&count=20`
  - Returns sellPrice, cashPrice (trade-in), exchangePrice, stock, images, category.
- **Important**: This is **not an official public API**. It can change or be restricted at any time. Use very politely (low volume, heavy caching, delays).
- **Status**: Implemented API-first with a public-page BS4 fallback and direct browser fallback.
- **Risk**: Medium (unofficial endpoint). Do not hammer it.

### Amazon UK
- **Website**: https://www.amazon.co.uk
- **Access**: Official Product Advertising API (PA-API) requires Amazon Associates account with sales. Alternatives: Keepa API (paid), or careful public-page approaches.
- **Notes**: New + used + renewed discs. Strong for comparison.
- **Status**: Implemented as a best-effort public-page BS4 client; WAF blocks soft-fail to search.

### Other major UK physical / retail
| Shop              | URL                          | Notes                              |
|-------------------|------------------------------|------------------------------------|
| **GAME**          | https://www.game.co.uk      | High-street + online. New & pre-owned. |
| Argos             | https://www.argos.co.uk     | Often competitive on new games.    |
| Smyths Toys       | https://www.smythstoys.com  | Family-friendly pricing.           |
| Very / Littlewoods| various                      | Occasional deals.                  |
| eBay UK           | https://www.ebay.co.uk      | Marketplace (used + new). Higher variance. |
| MusicMagpie / Decluttr | various                 | Trade-in focused.                  |

**Strategy**: Keep API sources primary, cache every public-search client, and retain a direct browser fallback when HTML changes or blocks automation.

---

## 4. Legitimate Digital Stores

Fanatical, Green Man Gaming, Humble, Gamesplanet, WinGameStore, IndieGala, GameBillet, GamersGate, etc. (mostly covered by aggregators).

---

## 5. Third-Party / Grey-Market Keyshops (USE WITH EXTREME CAUTION)

See previous detailed list (Loaded, G2A, Eneba, Kinguin, Instant Gaming, K4G, etc.).  
**Never aggressively scrape**. Prefer aggregator data. Always show risk warnings in the UI.

---

## 6. Newsletters & Deal Feeds

Steam, Epic, Humble, Fanatical, GG.deals, ITAD, r/GameDeals, r/FreeGameFindings, etc.

---

## 7. Environment configuration

`.env.example` is the authoritative template and contains only settings the current code reads: Django security/hosts, region, SQLite/PostgreSQL, bounded cache and I/O pools, Redis/Celery scheduling, and email backend/from-address. The project does not currently read Steam, GG.deals, ITAD, Epic, Keepa, Discord, or Telegram credentials.

---

## 8. Original implementation priority (historical)

This was the initial pilot plan and is retained for reference; the current implementation has expanded beyond it.

1. Django project skeleton + models (Game, Store, PriceRecord)
2. Pilot title: **God of War (PS4)**
3. Manual / polite CeX lookup for that title
4. Simple attractive comparison page (PSN digital vs CeX physical vs others)
5. Steam + GG.deals / ITAD for broader coverage
6. Amazon UK + more physical shops later

---

## Rules We Follow

- Prefer official & aggregator APIs
- Any unofficial endpoint (CeX internal) = low volume + heavy caching + easy to disable
- Never commit secrets
- Clearly label physical vs digital and risk level in the UI
- Attribute official sale pages separately from independent price trackers, and keep an official browse fallback when an automated home feed is unavailable
- Keep the product UK-first while treating every supported platform consistently

This keeps the project focused, legal, and sustainable.
