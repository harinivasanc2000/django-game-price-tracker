# 🎮 Django Game Price Tracker

**Track the best video game deals across Steam, Epic, and more — safely, every day.**

A clean Django web app that watches the games you care about and alerts you the moment a better price appears.  
Built with **public APIs only** so you stay clear of bans, rate-limit walls, and Terms-of-Service headaches.

---

## Why this project?

- 🔍 **Never miss a deal** — Steam sales, Epic free games, regional pricing, and key-shop offers in one place
- ⚡ **Daily automated checks** — runs in the background and notifies you only when something actually drops
- 🛡️ **Ban-proof by design** — uses official / public endpoints (Steam Store API, price aggregators, etc.) instead of aggressive scraping
- 📊 **Beautiful sorted list** — cheapest current price first, with discount % and history
- 📱 **Personal watchlists** — add any game, set a target price, get email / Discord / Telegram alerts

No grey-market scraping. No risk of getting your IP blocked. Just reliable, legal data.

---

## Core Idea

1. You pick the games you want to watch (by Steam App ID or title).
2. The app fetches current prices from trusted public sources.
3. Results are sorted ascending by price.
4. A scheduled task runs every day and notifies you on price drops or free giveaways.

---

## Tech Stack

| Layer              | Choice                          |
|--------------------|---------------------------------|
| Backend            | Django 5 + Django REST Framework |
| Task Queue         | Celery + Redis (or simple cron) |
| Price Sources      | Steam Store API (public), GG.deals, IsThereAnyDeal, etc. |
| Frontend           | Django Templates + HTMX / Alpine (or React later) |
| Notifications      | Email, Discord webhooks, Telegram bot |

---

## Safe Data Sources (public APIs first)

| Source              | Type              | Status        | Notes |
|---------------------|-------------------|---------------|-------|
| **Steam Store API** | Official public   | ✅ Ready     | `store.steampowered.com/api/appdetails` — free, rate-limited, perfect |
| **GG.deals API**    | Aggregator        | ✅ Recommended | Multi-store prices by Steam App ID |
| **IsThereAnyDeal**  | Aggregator        | Planned       | Excellent historical data |
| **Epic Games**      | Community wrapper | Planned       | Use carefully |
| Key shops (G2A…)    | Partner / paid    | Later         | Only via official partner APIs |

**Full details, API endpoints, rate limits, newsletters and environment-variable placeholders** are documented in:

📄 **[SOURCES.md](SOURCES.md)**

We start with Steam + aggregators. No direct scraping of reseller sites.

---

## Project Goals

- [x] Private GitHub repo + clean README
- [x] Comprehensive SOURCES.md (stores, APIs, newsletters)
- [ ] Django project skeleton + models (Game, Store, PriceRecord, Watchlist)
- [ ] Steam price client (already prototyped)
- [ ] Admin + simple list view sorted by price
- [ ] Daily Celery task + price-drop notifications
- [ ] User accounts & personal watchlists
- [ ] More public aggregators
- [ ] Optional key-shop support via official APIs only

---

## Quick Start (coming soon)

```bash
git clone https://github.com/harinivasanc2000/django-game-price-tracker.git
cd django-game-price-tracker
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

---

## Philosophy

> Use public APIs. Respect rate limits. Never get banned.  
> Focus on the deals that matter, not on fighting anti-bot systems.

Built with Django because we want something solid, maintainable, and fun to extend.

---

**Ready to hunt deals the smart way?**  
Star the repo, open an issue, or just start coding. Let's build it together.
