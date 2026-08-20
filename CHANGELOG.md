# Changelog

---

## 2026-08-20 16:00 BST — Disclaimer, deal news, safety

### Added
- **First-visit modal** on home (blurred backdrop + dialogue)
  - What the tool is / is not
  - Not responsible for purchases / keys / losses
  - Stored in `localStorage` (`gpt_disclaimer_v1`)
- **Deal & safety tips** on home (expandable)
- **Steam news filtered** to sale / discount / free / price headlines
- Detail sidebar: **Deal & price news**, **Stay safe**, ITAD / GG.deals links
- **Best GBP pick** tip under offer chips
- Platform chips **hide irrelevant panels** (e.g. PC hides pure PSN focus less)

```bash
git pull && python manage.py runserver
```

To see the disclaimer again: DevTools → Application → Local Storage → delete `gpt_disclaimer_v1`.
