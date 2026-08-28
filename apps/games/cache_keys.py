"""Shared UI cache keys.

Keeping versioned keys in one module prevents a write/action view from
invalidating an obsolete key while a page continues serving stale content.
"""

HOME_CARDS = "home:cards:v4"
SITE_SETTINGS = "site_settings:v1"
TRACKED_DRAWER = "tracked_drawer:v1"
