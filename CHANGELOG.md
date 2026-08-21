# Changelog

**Rule:** Never overwrite past entries. Always **prepend** new sections at the top (newest first).

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

```bash
git pull
# read DEVELOPER.md
python manage.py runserver
# http://127.0.0.1:8000/about/
```

---

## 2026-08-21 04:35 BST — Buy guide + public Steam / CheapShark feeds

- `/guide/`, Steam specials on home, multi-store deals on `/deals/`

---

## 2026-08-21 04:25 BST — Training CSV + detail digital panel

- `/export/training.csv`, digital store panel, similar games

---

## Earlier

See git log.
