# Changelog

---

## 2026-08-20 18:25 BST — Continue batch

### Fixed earlier
- Disclaimer **Continue** button (CSS `display:flex` overrode `hidden`)

### Added
- **Recently viewed** on home (from session browse history)
- Nav **Deals** → `/deals/`
- Press **`/`** anywhere to focus search
- Toast helper (`showToast`) for future copy/share actions
- Home quick links + safety tips + first-visit disclaimer

```bash
git pull && python manage.py runserver
```

### Still useful next
- [ ] Copy link / share on detail page
- [ ] Per-user watchlists (not global track)
- [ ] Discord webhook alerts
