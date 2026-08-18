# 🎮 Data Sources & Public APIs

This file documents **all legitimate stores, aggregators, public APIs, domains and newsletters** we plan to support, plus a large reference list of third-party / grey-market keyshops (with heavy warnings).

**Philosophy**: Prefer official / public APIs + reputable aggregators. Never hard-scrape keyshops. Store real API keys in environment variables or Django settings (never commit them).

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
- **AllKeyShop**, **Gocdkeys**, **KrakenKeys** – comparison sites (useful for research, not primary data sources)

---

## 3. Legitimate / Authorized-leaning Digital Stores

These generally source keys more cleanly (publisher / authorized distributor):

- **Fanatical** – https://www.fanatical.com (bundles + keys, publisher partnerships)
- **Green Man Gaming** – https://www.greenmangaming.com (authorized retailer)
- **Humble Bundle / Humble Store** – https://www.humblebundle.com
- **Gamesplanet** – https://gamesplanet.com
- **WinGameStore** – https://www.wingamestore.com
- **IndieGala** – https://www.indiegala.com
- **GameBillet** – https://www.gamebillet.com
- **GamersGate** – https://www.gamersgate.com

Almost all of the above are already covered by ITAD / GG.deals.

---

## 4. Third-Party / Grey-Market Keyshops (USE WITH EXTREME CAUTION)

> **⚠️ STRONG WARNING**  
> These sites often sell keys significantly cheaper than Steam/Epic (example: Assassin's Creed titles for ~£4 vs £8–10 on Steam). Many users report successful activations, including from Loaded.  
> **However**:  
> - Keys may come from regional arbitrage, bulk purchases, or sometimes questionable sources.  
> - Risk of key revocation, region locks, Steam account flags, or support refusal by publishers.  
> - Marketplaces (G2A, Kinguin, Eneba, etc.) have third-party sellers — quality varies wildly.  
> - This project will **never** scrape these sites aggressively. Prices should only be pulled via public aggregators (GG.deals / ITAD) when available.  
> - Buying is at your own risk. Prefer official stores + authorized resellers when possible.

### Direct Resellers (generally lower risk than open marketplaces)
| Site                    | URL                              | Notes / Risk Level                  |
|-------------------------|----------------------------------|-------------------------------------|
| **Loaded** (ex-CDKeys) | https://www.loaded.com          | Most established direct reseller. User reports of working cheap keys (e.g. AC titles). Medium risk. |
| Instant Gaming          | https://www.instant-gaming.com  | Popular direct reseller. Medium risk. |
| K4G (Keys4Games)        | https://k4g.com                 | Large selection, competitive prices. Medium-High. |
| GameBoost               | https://gameboost.com           | Key reseller. Medium-High. |
| Difmark                 | https://difmark.com             | Higher risk reports in some communities. |

### Open Marketplaces (higher risk — seller-dependent)
| Site          | URL                         | Notes / Risk Level                     |
|---------------|-----------------------------|----------------------------------------|
| **G2A**       | https://www.g2a.com        | Largest marketplace. Past controversies. Use high-rated sellers + protection if available. High risk. |
| **Eneba**     | https://www.eneba.com      | Clean UI, buyer protection. Still third-party sellers. Medium-High. |
| **Kinguin**   | https://www.kinguin.net    | Old marketplace. Buyer protection options. Medium-High. |
| Gamivo        | https://www.gamivo.com     | Marketplace + some direct. Medium-High. |
| Driffle       | https://driffle.com        | Marketplace. Higher caution advised. |
| Electronic First | https://www.electronicfirst.com | Marketplace style. |
| HRKGame       | https://www.hrkgame.com    | Older keyshop / marketplace. |
| MMOGA         | https://www.mmoga.com      | Long-running but mixed reputation. |
| YuPlay        | (various regional)         | Often region-focused. |
| LootBar       | https://www.lootbar.gg     | More known for top-ups; also keys. |
| GameSeal      | (search current domain)    | Emerging marketplace. |
| SCDKey / similar smaller shops | various | Many small clone sites exist — higher scam risk. |

### Other / Smaller / Regional Keyshops (higher scrutiny needed)
These appear frequently in comparisons but vary greatly in reliability:

- AllKeyShop (comparison + redirects)
- Gocdkeys / ClaveCD style comparison sites
- PremiumCDkeys, Wyrel, and many short-lived domains
- Various regional shops (Russia, Turkey, LATAM, Asia-focused key sites)
- Bundle-focused or gift-card heavy sites that also sell keys

**There are dozens more small or short-lived sites.** New ones appear and disappear regularly. Always:
1. Check recent Trustpilot / Reddit feedback
2. Prefer sites with clear buyer protection
3. Use PayPal or credit cards that allow chargebacks when possible
4. Never buy from unknown one-page shops

---

## 5. Newsletters & Deal Feeds (Great for alerts)

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

## 6. Environment Variables Template

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

## 7. Implementation Priority (Django)

1. **Steam Store API** – zero key, immediate value
2. **GG.deals API** – multi-store prices with one call (includes many of the shops above)
3. **IsThereAnyDeal API** – historical lows + more shops
4. Epic free games / community wrappers
5. Partner APIs only if needed later
6. Direct keyshop scraping – **avoid** (high ban risk + ToS issues)

---

## Rules We Follow

- Never scrape HTML of keyshops aggressively
- Always respect rate limits + robots.txt
- Cache responses (Redis / Django cache)
- Attribute sources when required by ToS
- Store secrets in environment variables only
- Clearly label any grey-market prices in the UI with risk warnings

This keeps the project clean, legal, and ban-resistant while still letting users discover the cheapest available deals (including the ones you found on Loaded).
