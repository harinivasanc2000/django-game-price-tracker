from django.contrib import admin
from .models import (
    Game,
    Store,
    PriceRecord,
    BrowseHistory,
    SiteSettings,
    AdminChangeLog,
)


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ("name", "store_type", "country", "is_active", "website")
    list_filter = ("store_type", "country", "is_active")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "platform",
        "steam_app_id",
        "launch_price",
        "launch_currency",
        "is_active",
        "updated_at",
    )
    list_filter = ("platform", "is_active")
    search_fields = ("title", "slug", "steam_app_id")
    prepopulated_fields = {"slug": ("title",)}
    fieldsets = (
        (None, {"fields": ("title", "slug", "platform", "steam_app_id", "psn_id", "cover_url", "release_year", "is_active")}),
        (
            "Launch / MSRP (public reference)",
            {"fields": ("launch_price", "launch_currency", "launch_price_source")},
        ),
        ("Admin product notes", {"fields": ("admin_notes",)}),
    )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        AdminChangeLog.objects.create(
            actor=getattr(request.user, "username", "admin") or "admin",
            action="game_save" if change else "game_create",
            details=f"{obj.title} ({obj.platform}) launch={obj.launch_price} {obj.launch_currency}",
        )


@admin.register(PriceRecord)
class PriceRecordAdmin(admin.ModelAdmin):
    list_display = (
        "game", "store", "price", "original_price", "currency",
        "is_physical", "is_used", "in_stock", "recorded_at",
    )
    list_filter = ("store", "is_physical", "is_used", "currency", "in_stock")
    search_fields = ("game__title", "store__name")
    date_hierarchy = "recorded_at"
    raw_id_fields = ("game", "store")


@admin.register(BrowseHistory)
class BrowseHistoryAdmin(admin.ModelAdmin):
    list_display = ("action", "title", "query", "steam_app_id", "created_at", "session_key")
    list_filter = ("action",)
    search_fields = ("title", "query", "session_key")
    date_hierarchy = "created_at"


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    list_display = ("site_title", "wallpaper", "show_launch_prices", "updated_at")

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        AdminChangeLog.objects.create(
            actor=getattr(request.user, "username", "admin") or "admin",
            action="site_settings",
            details=f"wallpaper={obj.wallpaper} title={obj.site_title}",
        )


@admin.register(AdminChangeLog)
class AdminChangeLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor", "action", "details")
    list_filter = ("action", "actor")
    search_fields = ("action", "details", "actor")
    readonly_fields = ("created_at", "actor", "action", "details")
