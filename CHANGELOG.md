# Changelog — full project log

---

## 2026-08-20 15:15 BST — Finish watch alerts + GBP charts (on top of local work)

### Already in your tree (local commits)
- `apps/games/fx.py` — USD/EUR → GBP via open.er-api.com (+ fallback rates)
- `apps/games/cache.py` — request dedupe / short TTL cache
- `Watch` + `PriceAlert` models; alert checks in Celery refresh
- Console email backend + `SITE_URL`
- Live offers sorted by **GBP**

### Completed this pass
- Migration `0004_watch_pricealert`
- Admin for Watch + PriceAlert
- **Chart series all in GBP** (fair average)
- Offer chips show `≈ £x.xx` when currency is not GBP
- Detail page: **Watch price** form (target under £…) after Track
- Profile: watches, alerts, mark-read
- Watch redirect stays on Steam detail when possible

### How to use alerts
```bash
git pull
python manage.py migrate
# set email on your user in admin
python manage.py runserver
# Track a game → Watch price with target
python manage.py refresh_prices   # checks targets; emails print to console
```

### Still TODO
- [ ] SMS / Discord webhook alerts
- [ ] Per-user tracked list (not global is_active)
- [ ] Stronger CeX when API allows

---

## 2026-08-19 — Platforms, PSN, UK stores, news, Celery, graph dropdown

See earlier entries in git history for full detail.

```bash
git pull && python manage.py migrate && python manage.py runserver
```
