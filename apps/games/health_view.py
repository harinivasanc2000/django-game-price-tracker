"""Simple health / diagnostics endpoint."""
from django.http import JsonResponse
from django.db import connection


def health(request):
    db_ok = False
    try:
        with connection.cursor() as c:
            c.execute("SELECT 1")
            db_ok = True
    except Exception as e:
        return JsonResponse({"ok": False, "db": False, "error": str(e)[:120]}, status=503)

    extras = {}
    try:
        from bs4 import BeautifulSoup  # noqa: F401

        extras["beautifulsoup4"] = True
    except ImportError:
        extras["beautifulsoup4"] = False
    try:
        import lxml  # noqa: F401

        extras["lxml"] = True
    except ImportError:
        extras["lxml"] = False

    return JsonResponse({"ok": True, "db": db_ok, **extras})
