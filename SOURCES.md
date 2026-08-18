# 🎮 Data Sources & Public APIs

This file documents **all legitimate stores, aggregators, public APIs, domains and newsletters** we plan to support, plus third-party keyshops and **UK physical resellers**.

**Current focus**: United Kingdom + PlayStation games (pilot title: God of War PS4).

**Philosophy**: Prefer official / public APIs + reputable aggregators. Be extremely careful with any internal/unofficial endpoints (e.g. CeX). Store secrets in environment variables only.

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
- **Env placeholder**: `STEAM_API_KEY=` (optional)

### PlayStation Store (PSN)
- **Website**: https://store.playstation.com/en-gb/
- **Access**: No simple free public price API. Community wrappers and third-party services (PlatPrices, PSprices) exist.
- **Notes**: Primary digital source for PS4/PS5. Region = GB for UK.
- **Status**: Track via aggregators / community tools first.

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
- **Env**: `GGDEALS_API_KEY=`
- **Status**: ✅ Top priority

### IsThereAnyDeal (ITAD)
- **Website**: https://isthereanydeal.com
- **Docs**: https://docs.isthereanydeal.com
- **Env**: `ITAD_API_KEY=`
- **Status**: ✅ Strongly recommended

### Other
- CheapShark, PSprices (good for PlayStation), PlatPrices, Hot.Game

---

## 3. UK Physical Resellers (New Focus)

We are starting with **physical discs** in the UK, especially PlayStation.

### CeX (uk.webuy.com)
- **Website**: https://uk.webuy.com
- **Type**: Second-hand + some new. Excellent for cheap used PS4/PS5 games.
- **Internal API** (community reverse-engineered):
  - Base: `https://wss2.cex.uk.webuy.io/v3/`
  - Search example: `/boxes?q=God+of+War&firstRecord=1&count=20`
  - Returns sellPrice, cashPrice (trade-in), exchangePrice, stock, images, category.
- **Important**: This is **not an official public API**. It can change or be restricted at any time. Use very politely (low volume, heavy caching, delays).
- **Status**: Pilot target for God of War PS4.
- **Risk**: Medium (unofficial endpoint). Do not hammer it.

### Amazon UK
- **Website**: https://www.amazon.co.uk
- **Access**: Official Product Advertising API (PA-API) requires Amazon Associates account with sales. Alternatives: Keepa API (paid), or careful public-page approaches.
- **Notes**: New + used + renewed discs. Strong for comparison.
- **Status**: Later (after CeX pilot).

### Other major UK physical / retail
| Shop              | URL                          | Notes                              |
|-------------------|------------------------------|------------------------------------|
| **GAME**          | https://www.game.co.uk      | High-street + online. New & pre-owned. |
| Argos             | https://www.argos.co.uk     | Often competitive on new games.    |
| Smyths Toys       | https://www.smythstoys.com  | Family-friendly pricing.           |
| Very / Littlewoods| various                      | Occasional deals.                  |
| eBay UK           | https://www.ebay.co.uk      | Marketplace (used + new). Higher variance. |
| MusicMagpie / Decluttr | various                 | Trade-in focused.                  |

**Strategy**: Start with CeX (interesting second-hand prices) + official PSN digital, then expand to Amazon UK and GAME.

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

## 7. Environment Variables Template

```env
# Official / Aggregators
STEAM_API_KEY=
GGDEALS_API_KEY=
ITAD_API_KEY=

# Optional later
EPIC_API_KEY=
KEEP A_API_KEY=          # for Amazon price history if used

# Notifications
DISCORD_WEBHOOK_URL=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=
```

---

## 8. Implementation Priority (Current)

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
- Start UK + PlayStation, expand later

This keeps the project focused, legal, and sustainable.
