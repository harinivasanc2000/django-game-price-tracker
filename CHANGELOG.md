# Changelog & status

---

## Fixed (this pass)

| Issue | Fix |
|-------|-----|
| `UNIQUE constraint failed: games_game.slug` on `seed_launch_prices` | Seed no longer overwrites slug into a collision; updates by `steam_app_id` or creates with `title-pc-{appid}` fallback |
| Track redirected to compare; details only after track | **Title click** loads full detail: Steam price, launch ref, chart, multi-store deals |
| Track/Untrack changed page / home spam | Track & Untrack **stay on the same detail page**; no home flash messages |
| Only Steam for comparison | **CheapShark** public API on detail page (Steam, GOG, Humble, Fanatical, GMG, Epic, etc. — USD) |

---

## Admin-driven changes

| Area | Where |
|------|--------|
| Wallpaper | Site settings: comet / gradient / none |
| Launch MSRP | Game: `launch_price`, source |
| Product notes | Game: `admin_notes` |
| Audit | Admin change log |

```bash
python manage.py seed_launch_prices   # safe to re-run after slug fix
```

---

## Done

- Clean home (search → tracked → popular)
- Typeahead search, DLC ranking, free vs unknown
- Comet wallpaper, tracked drawer, login/profile
- Detail page = single place for prices + stores + track

---

## Next (not done yet)

- [ ] Daily Celery refresh of tracked Steam prices
- [ ] Email / Discord price-drop alerts
- [ ] GG.deals / ITAD for true multi-year history (needs keys)
- [ ] Per-user watchlists (currently global active games)
- [ ] CeX / Amazon UK / PSN physical + digital UK
- [ ] Convert CheapShark USD ↔ GBP display
- [ ] AJAX track button (no full page reload)
- [ ] Reduced-motion / disable wallpaper toggle for users

---

## Login

No default password. Create outside VS Code if the integrated terminal crashes:

```bash
python manage.py createsuperuser
# or
python manage.py shell -c "from django.contrib.auth import get_user_model; U=get_user_model(); U.objects.create_superuser('admin','a@a.com','YourPassword')"
```
