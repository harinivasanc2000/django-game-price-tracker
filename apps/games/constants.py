"""
Shared constants — edit here instead of hunting through views.

POPULAR_APP_IDS  → home page grid order
PLATFORMS        → search / filter dropdowns
STORE_PLATFORMS  → detail page platform chips
"""

# Steam App IDs shown on the home "Popular" grid (order = display order).
# Add or remove IDs any time; no migration needed.
POPULAR_APP_IDS: list[int] = [
    1091500,  # Cyberpunk 2077
    1245620,  # ELDEN RING
    271590,  # GTA V
    1174180,  # RDR2
    1593500,  # God of War
    1086940,  # Baldur's Gate 3
    292030,  # Witcher 3
    1817070,  # Spider-Man Remastered
    814380,  # Sekiro
    1888930,  # The Last of Us Part I
    2050650,  # Resident Evil 4
    1145360,  # Hades
]

# (value, label) for platform filters
PLATFORMS: list[tuple[str, str]] = [
    ("", "All"),
    ("pc", "PC"),
    ("ps4", "PS4"),
    ("ps5", "PS5"),
    ("xbox", "Xbox"),
    ("switch", "Switch"),
]

STORE_PLATFORMS: list[tuple[str, str]] = [
    ("pc", "PC"),
    ("ps4", "PS4"),
    ("ps5", "PS5"),
    ("xbox", "Xbox"),
    ("switch", "Switch"),
]
