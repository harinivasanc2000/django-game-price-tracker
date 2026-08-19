# Changelog & status

---

## Admin-driven changes (for later data/UI updates)

Controlled from **Django admin** (`/admin/`) as staff. Saves also go to **Admin change log**.

| Area | Where | What |
|------|--------|------|
| Wallpaper | Site settings | comet / gradient / none |
| Site title, footer | Site settings | Branding |
| Launch / MSRP | Game: launch_price, currency, source | Public reference |
| Product notes | Game: admin_notes | Free text |
| Audit | Admin change log | Who changed what |

```bash
python manage.py seed_launch_prices
```

---

## This pass

- Light **comet rain** wallpaper (~8 comets, ~30fps)
- Admin **Site settings** for wallpaper/UI
- Nav: **Log in** vs **Profile / Settings**
- **Tracked** = right-side **drawer** with titles
- Cleaner home (search-first)
- **Launch prices** seeded + chart baseline
- **AdminChangeLog** for explicit admin updates

---

## Login password

**No default admin id/password.** Create one:

```bash
python manage.py createsuperuser
```

Then `/accounts/login/` or `/admin/`.

---

## Backlog

- Daily price refresh (Celery)
- Discord/Telegram alerts
- GG.deals / ITAD history
- Per-user watchlists
- CeX / Amazon / PSN UI
- CSV launch-price import
- Reduced-motion option
- Region picker in UI
