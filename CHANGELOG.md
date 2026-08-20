# Changelog

---

## 2026-08-20 19:50 BST — Clean home (deal-site style)

### Removed from home main screen
- **Recently viewed** (still in History)
- **Tracked list** (still in right drawer + Profile)

### Added (inspired by ITAD / GG.deals / Steam store)
- **Hero search** only on home
- **Popular grid** with Steam header images + live UK prices
- Discount pills + lowest GBP when tracked multi-store exists
- **On sale vs launch** hot strip
- Parallel Steam detail fetch (cached) for popular IDs

```bash
git pull && python manage.py runserver
```

First load of popular cards may take a second while Steam prices cache.
