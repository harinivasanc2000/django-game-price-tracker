from django.conf import settings
from django.db import models
from django.utils.text import slugify


class Store(models.Model):
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
    store_type = models.CharField(max_length=20, choices=StoreType.choices, default=StoreType.OFFICIAL)
    country = models.CharField(max_length=2, default="GB")
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
    psn_id = models.CharField(max_length=100, blank=True)
    cover_url = models.URLField(blank=True)
    release_year = models.PositiveSmallIntegerField(null=True, blank=True)
    # Public reference launch / MSRP (manual or seeded from known public figures)
    launch_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Approximate public launch/MSRP price for this platform/edition",
    )
    launch_currency = models.CharField(max_length=3, default="GBP", blank=True)
    launch_price_source = models.CharField(
        max_length=255,
        blank=True,
        help_text="Where this launch price came from (admin note)",
    )
    admin_notes = models.TextField(blank=True, help_text="Editable product notes (admin)")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return f"{self.title} ({self.get_platform_display()})"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(f"{self.title}-{self.platform}")
        super().save(*args, **kwargs)


class PriceRecord(models.Model):
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="prices")
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="prices")
    price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="GBP")
    original_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    discount_percent = models.PositiveSmallIntegerField(null=True, blank=True)
    url = models.URLField(blank=True)
    is_physical = models.BooleanField(default=False)
    is_used = models.BooleanField(default=False)
    condition = models.CharField(max_length=50, blank=True)
    in_stock = models.BooleanField(default=True)
    recorded_at = models.DateTimeField(auto_now_add=True)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["price", "-recorded_at"]
        indexes = [
            models.Index(fields=["game", "store", "-recorded_at"]),
            # Fast "last snapshot per game" lookups used by the compare page.
            models.Index(fields=["game", "-recorded_at"]),
            # Background refresh scans: newest first.
            models.Index(fields=["-recorded_at"]),
        ]

    def __str__(self):
        return f"{self.game.title} @ {self.store.name}: {self.price} {self.currency}"


class Watch(models.Model):
    """A user following a tracked game (per-game, per-user)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="watches"
    )
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="watches")
    target_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Optional: alert me when the GBP price drops below this",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "game"], name="unique_user_game_watch")
        ]
        indexes = [models.Index(fields=["game", "user"])]

    def __str__(self):
        return f"{self.user.username} -> {self.game.title}"


class PriceAlert(models.Model):
    """One fire-and-forget notification: emitted when a watch target is hit."""

    watch = models.ForeignKey(Watch, on_delete=models.CASCADE, related_name="alerts")
    price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="GBP")
    target_price = models.DecimalField(max_digits=10, decimal_places=2)
    store = models.CharField(max_length=120, blank=True)
    url = models.URLField(blank=True)
    is_sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["is_sent", "-created_at"])]

    def __str__(self):
        return f"Alert {self.watch_id} @ {self.price} {self.currency}"


class BrowseHistory(models.Model):
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
    # Indexed so the occasional cleanup prune is fast.
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            # Power the "recent items for this session" query on the
            # history page (session_key is already db_indexed).
            models.Index(fields=["session_key", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.action}: {self.title or self.query}"


class SiteSettings(models.Model):
    """Singleton-style site UI settings (edit in Django admin)."""

    class Wallpaper(models.TextChoices):
        COMET = "comet", "Comet rain (light)"
        GRADIENT = "gradient", "Soft red gradient"
        NONE = "none", "Solid dark"

    site_title = models.CharField(max_length=120, default="Game Price Tracker")
    wallpaper = models.CharField(
        max_length=20, choices=Wallpaper.choices, default=Wallpaper.COMET
    )
    show_launch_prices = models.BooleanField(default=True)
    footer_text = models.CharField(
        max_length=255,
        blank=True,
        default="Public Steam data · Launch prices are approximate public references",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Site settings"
        verbose_name_plural = "Site settings"

    def __str__(self):
        return "Site settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class AdminChangeLog(models.Model):
    """Explicit log of admin/data changes for later updates."""

    created_at = models.DateTimeField(auto_now_add=True)
    actor = models.CharField(max_length=120, blank=True, default="admin")
    action = models.CharField(max_length=120)
    details = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d} {self.action}"
