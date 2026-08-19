from django.db import models
from django.utils.text import slugify


class Store(models.Model):
    """Retailer or platform (Steam, PSN, CeX, Amazon UK, Loaded, etc.)."""

    class StoreType(models.TextChoices):
        OFFICIAL = "official", "Official Platform"
        AGGREGATOR = "aggregator", "Price Aggregator"
        AUTHORIZED = "authorized", "Authorized Reseller"
        PHYSICAL = "physical", "Physical / High-street"
        KEYSHOP = "keyshop", "Keyshop / Grey market"
        MARKETPLACE = "marketplace", "Open Marketplace"

    name = models.CharField(max_length=120)
    slug = models.SlugField(unique=True)
    website = models.URLField(blank=True)
    store_type = models.CharField(
        max_length=20, choices=StoreType.choices, default=StoreType.OFFICIAL
    )
    country = models.CharField(max_length=2, default="GB", help_text="ISO country code")
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Game(models.Model):
    """A game we track (digital or physical)."""

    class Platform(models.TextChoices):
        PS4 = "ps4", "PlayStation 4"
        PS5 = "ps5", "PlayStation 5"
        PC = "pc", "PC"
        XBOX = "xbox", "Xbox"
        SWITCH = "switch", "Nintendo Switch"
        OTHER = "other", "Other"

    title = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    platform = models.CharField(max_length=20, choices=Platform.choices, default=Platform.PS4)
    steam_app_id = models.PositiveIntegerField(null=True, blank=True, unique=True)
    psn_id = models.CharField(max_length=100, blank=True, help_text="PlayStation Store product ID if known")
    cover_url = models.URLField(blank=True)
    release_year = models.PositiveSmallIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return f"{self.title} ({self.get_platform_display()})"

    def save(self, *args, **kwargs):
        if not self.slug:
            base = f"{self.title}-{self.platform}"
            self.slug = slugify(base)
        super().save(*args, **kwargs)


class PriceRecord(models.Model):
    """A single price observation for a game at a store."""

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="prices")
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="prices")
    price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="GBP")
    original_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Retail / list price (Steam initial) — base for discount graphs",
    )
    discount_percent = models.PositiveSmallIntegerField(null=True, blank=True)
    url = models.URLField(blank=True)
    is_physical = models.BooleanField(default=False, help_text="True for disc / physical copy")
    is_used = models.BooleanField(default=False, help_text="True for second-hand (e.g. CeX)")
    condition = models.CharField(max_length=50, blank=True, help_text="e.g. Grade A, Renewed")
    in_stock = models.BooleanField(default=True)
    recorded_at = models.DateTimeField(auto_now_add=True)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["price", "-recorded_at"]
        indexes = [
            models.Index(fields=["game", "store", "-recorded_at"]),
        ]

    def __str__(self):
        kind = "used" if self.is_used else ("physical" if self.is_physical else "digital")
        return f"{self.game.title} @ {self.store.name}: {self.price} {self.currency} ({kind})"


class BrowseHistory(models.Model):
    """Browser-like history of searches and title views (session-based)."""

    class Action(models.TextChoices):
        SEARCH = "search", "Search"
        VIEW = "view", "View title"
        TRACK = "track", "Track price"

    session_key = models.CharField(max_length=64, db_index=True)
    action = models.CharField(max_length=10, choices=Action.choices)
    query = models.CharField(max_length=255, blank=True)
    steam_app_id = models.PositiveIntegerField(null=True, blank=True)
    title = models.CharField(max_length=255, blank=True)
    detail_url = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action}: {self.title or self.query} @ {self.created_at}"
