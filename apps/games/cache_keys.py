"""Shared UI cache keys.

Keeping versioned keys in one module prevents a write/action view from
invalidating an obsolete key while a page continues serving stale content.
"""

HOME_CARDS = "home:cards:v4"
# Console home feeds have separate keys so a PS4 response can never leak into
# PS5/Xbox/Switch selection.  The tuple also makes write-time invalidation
# explicit for cache backends that cannot delete by prefix.
HOME_PLATFORM_CARDS = "home:platform:v1"
HOME_PLATFORM_CARD_KEYS = tuple(
    f"{HOME_PLATFORM_CARDS}:{platform}"
    for platform in ("ps4", "ps5", "xbox", "switch")
)
SITE_SETTINGS = "site_settings:v1"
TRACKED_DRAWER = "tracked_drawer:v1"
