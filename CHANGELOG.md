# Changelog

**Rule:** Never overwrite past entries. Always **prepend** new sections at the top (newest first).

---

## 2026-08-27 17:45 BST — Detail speed + presets + leaner UK

### Performance
- **`platform_bundle` cached 3 min** (`pb:v2`) — platform AJAX + reloads reuse data
- Detail pool timeout **9s**; UK physical pool **8s**; HTML fetches **6s**
- Single Game query on detail (active + launch in one hit)
- Skip Amazon scrape when condition=`used`
- Smaller per-store limits on focused platform views

### Search UX
- Quick presets: **Under £10 / £20 / £40**, Any price, Cheapest first

### Home
- Solid cards (already lean); keep disclaimer without heavy blur dependency in new CSS paths

```bash
git pull
python manage.py runserver
```

---

## Earlier

See git log.
