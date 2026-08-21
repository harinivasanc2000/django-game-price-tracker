# Changelog

**Rule:** Never overwrite past entries. Always **prepend** new sections at the top (newest first).

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

```bash
git pull
python manage.py runserver
# Open a game → filter PS5 / Xbox / Switch
# Compare official price chips vs CeX / GAME / Smyths rows
```

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
