# Changelog

**Rule:** Never overwrite past entries. Always **prepend** new sections at the top (newest first).

---

## 2026-08-25 14:35 BST — More improvements

### Relevance
- **PSN** over-fetch + `title_match` (less DLC / wrong-edition noise)
- **Xbox** same pattern + cache key bump
- **Amazon UK** BS4 over-fetch ×3 → title_match; used/renewed detection

### UX
- Console panel icons (PS / Xbox / Switch)
- Search page icons + lighter solid cards
- Click any **price** to copy (toast confirm) — include `_copy_price.js.html`
- Health: `GET /health/?stores=1` pings CeX API + Steam lightly

```bash
git pull
python manage.py runserver
```

---

## 2026-08-24 — Icons + BS4 policy + local stores

See prior entries / git log.
