# Changelog

---

## 2026-08-20 19:10 BST — UI & feature batch

### Search
- Sort: relevance / price ↑↓ / biggest discount / name
- **Hide likely DLC** toggle (on by default)
- Cleaner result cards

### Deals
- **Export JSON** at `/export/tracked.json`
- Link from Best deals page

### Detail (partial)
- `_detail_actions.html` partial: **Copy link**, **Share**, savings badge
  (wire into steam_detail by including where Track buttons are)

### Earlier still active
- Recently viewed, `/` search focus, disclaimer, platform AJAX, deal news filter

```bash
git pull && python manage.py runserver
```
