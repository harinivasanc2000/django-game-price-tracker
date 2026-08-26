# Changelog

**Rule:** Never overwrite past entries. Always **prepend** new sections at the top (newest first).

---

## 2026-08-26 20:40 BST — Search optimise + filters + leaner Steam/Nintendo

### Search filters (server-side)
- Min / max £, **Hide DLC**, **Hide free**, sort including **Best title match**
- Filters included in multi-platform cache key (`mps:v5`)

### Runtime / RAM
- Multi-platform pool hard deadline **6s** (was 8)
- Modest over-fetch only (`limit+4`), not ×2–×3 everywhere
- Steam: max **2** alias queries, 4-conn pool, shorter timeouts, smaller detail payloads
- Nintendo: title_match + 7s HTML budget
- Query strings capped at 120 chars

### UX
- **Recent searches** on empty search page (session history, no network)
- Match score badge on Steam rows when available

```bash
git pull
python manage.py runserver
```

---

## Earlier

See git log.
