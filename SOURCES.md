# 🎮 Data Sources & Public APIs

This file documents **all legitimate stores, aggregators, public APIs, domains and newsletters** we plan to support.

**Philosophy**: Prefer official / public APIs only. Never hard-scrape keyshops. Store real API keys in environment variables or Django settings (never commit them).

---

## 1. Official Platforms (Best & Safest)

### Steam
- **Website**: https://store.steampowered.com
- **Public Store API** (no key required for basic prices):
  ```
  GET https://store.steampowered.com/api/appdetails?appids={APP_ID}&cc={COUNTRY_CODE}&filters=price_overview
  ```
- **Rate limit**: ~200 requests / 5 minutes
- **Notes**: Best starting point. Returns `price_overview` with final/initial price in cents + discount %.
- **API Key needed?**: No for store prices. (Steam Web API key is only needed for other endpoints)
- **Env placeholder**: `STEAM_API_KEY=` (optional)
- **Docs**: https://partner.steamgames.com / community reverse-engineered docs

### Epic Games Store
- **Website**: https://store.epicgames.com
- **Public / Community access**: Limited official public API. Community wrappers exist (e.g. epicstore_api Python package).
- **Free games endpoint**: Often available via GraphQL or public endpoints.
- **API Key needed?**: Usually no for basic catalog, but fragile.
- **Env placeholder**: `EPIC_API_KEY=` (if using paid/partner access later)
- **Status**: Planned – use carefully / via aggregators first.

### Ubisoft Connect / Ubisoft Store
- **Website**: https://store.ubisoft.com / https://www.ubisoft.com
- **Public API**: Very limited for third parties. Mostly internal / partner.
- **Notes**: Better to track via aggregators (ITAD / GG.deals) than direct.
- **Env placeholder**: `UBISOFT_API_KEY=` (partner only)
- **Status**: Low priority – use aggregator data.

### Rockstar Games Launcher / Social Club
- **Website**: https://www.rockstargames.com
- **Public API**: No useful public price API. Launcher uses internal endpoints.
- **Notes**: Track Rockstar titles via Steam (many are also on Steam) or aggregators.
- **Env placeholder**: N/A
- **Status**: Via Steam / aggregators only.

---

## 2. Price Aggregators (Highly Recommended)

These are the **smartest** way to get multi-store prices without scraping individual shops.

### GG.deals
- **Website**: https://gg.deals
- **API Docs**: https://gg.deals/api/
- **Key endpoint**:
  ```
  GET https://api.gg.deals/v1/prices/by-steam-app-id/?ids={APP_IDS}&key={YOUR_KEY}&region={REGION}
  ```
- **Free tier**: Available for personal / open-source (attribution required)
- **Rate limits**: 100 records/min, 1000/hour (free)
- **Env placeholder**: `GGDEALS_API_KEY=your_key_here`
- **How to get key**: Register at gg.deals → settings → generate API key
- **Status**: ✅ Top priority after Steam

### IsThereAnyDeal (ITAD)
- **Website**: https://isthereanydeal.com
- **API Docs**: https://docs.isthereanydeal.com /
- **Registration**: https://isthereanydeal.com/apps/my/
- **Auth**: API key or OAuth
- **Rate limit**: ~1000 requests / 5 min (verified accounts)
- **Env placeholder**: `ITAD_API_KEY=your_key_here`
- **Notes**: Excellent historical lows + shop list. Must follow their ToS (attribution, no competition).
- **Status**: ✅ Strongly recommended

### Other Aggregators (Future)
- **CheapShark** – good free API for deals
- **PSprices** – multi-platform (Steam + consoles)
- **Hot.Game** – has a free public API for some data

---

## 3. Legitimate Key / Digital Stores

We only consider stores that source keys legally (authorized distributors / publishers).

### Loaded (formerly CDKeys)
- **Website**: https://www.loaded.com
- **Public API**: No public developer API for prices (as of 2026)
- **Notes**: Claims official sources. Track via aggregators only for now.
- **Env placeholder**: N/A (or partner later)
- **Status**: Via GG.deals / ITAD

### G2A
- **Website**: https://www.g2a.com
- **API**: Partner / Export API exists (OAuth) – requires approval as seller/buyer partner.
- **Docs**: https://www.g2a.com/integration-api/
- **Notes**: Marketplace (third-party sellers). Higher risk of grey keys. Prefer aggregators.
- **Env placeholder**: `G2A_CLIENT_ID=` + `G2A_CLIENT_SECRET=` (partner only)
- **Status**: Low priority / partner only

### Other legitimate-leaning stores
- Fanatical, Humble Bundle, Green Man Gaming, Gamesplanet, WinGameStore, etc.
- Almost all are best covered by **ITAD** or **GG.deals**.

---

## 4. Newsletters & Deal Feeds (Great for alerts)

These can be used for free-game / big-sale notifications:

| Name                  | Website / Signup                     | Notes                              |
|-----------------------|--------------------------------------|------------------------------------|
| Steam                 | store.steampowered.com               | Wishlist + sale emails             |
| Epic Games            | store.epicgames.com                  | Free game announcements            |
| Humble Bundle         | humblebundle.com                     | Weekly deals + Choice              |
| Fanatical             | fanatical.com                        | Bundle & sale newsletters          |
| GG.deals              | gg.deals                             | Deal alerts                        |
| IsThereAnyDeal        | isthereanydeal.com                   | Price alerts + waitlist            |
| Reddit r/GameDeals    | reddit.com/r/GameDeals               | Community + bot feeds              |
| FreeGameFindings      | reddit.com/r/FreeGameFindings        | Free keys & giveaways              |

---

## 5. Environment Variables Template

Create a `.env` file (never commit it) or use Django settings:

```env
# Official
STEAM_API_KEY=

# Aggregators (get free keys)
GGDEALS_API_KEY=
ITAD_API_KEY=

# Optional / Partner later
EPIC_API_KEY=
G2A_CLIENT_ID=
G2A_CLIENT_SECRET=
UBISOFT_API_KEY=

# Notifications
DISCORD_WEBHOOK_URL=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=
```

---

## 6. Implementation Priority (Django)

1. **Steam Store API** – zero key, immediate value
2. **GG.deals API** – multi-store prices with one call
3. **IsThereAnyDeal API** – historical lows + more shops
4. Epic free games / community wrappers
5. Partner APIs only if needed later

---

## Rules We Follow

- Never scrape HTML of keyshops aggressively
- Always respect rate limits + robots.txt
- Cache responses (Redis / Django cache)
- Attribute sources when required by ToS
- Store secrets in environment variables only

This keeps the project clean, legal, and ban-resistant.
