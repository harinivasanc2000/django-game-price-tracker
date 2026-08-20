# Changelog

---

## 2026-08-20 15:45 BST — Detail polish

### UI
- **News + social in sticky scrollable sidebar**; main column = prices & deals only
- **Graph: change-only points** (flat 19–22 collapses; next point is the next real change)
- **Platform chips (PC/PS4/PS5/Xbox/Switch/All)** switch via AJAX — **no full page reload**
- Steam **Windows / Mac / Linux** shown as OS badges (from Steam API)
- **Per-game wallpaper** from Steam `library_hero` / page background / header art
- Parallel fetch for deals + PSN/UK + news on title open
- Wider layout on detail pages

### API
- `GET /api/platform/<app_id>/?platform=ps5` — JSON for platform panels

```bash
git pull && python manage.py runserver
```
