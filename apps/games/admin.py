from django.contrib import admin
from .models import Game, Store, PriceRecord


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ("name", "store_type", "country", "is_active", "website")
    list_filter = ("store_type", "country", "is_active")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ("title", "platform", "steam_app_id", "is_active", "updated_at")
    list_filter = ("platform", "is_active")
    search_fields = ("title", "slug", "steam_app_id")
    prepopulated_fields = {"slug": ("title",)}


@admin.register(PriceRecord)
class PriceRecordAdmin(admin.ModelAdmin):
    list_display = (
        "game",
        "store",
        "price",
        "currency",
        "is_physical",
        "is_used",
        "in_stock",
        "recorded_at",
    )
    list_filter = ("store", "is_physical", "is_used", "currency", "in_stock")
    search_fields = ("game__title", "store__name")
    date_hierarchy = "recorded_at"
    raw_id_fields = ("game", "store")
