from django.contrib import admin

from .models import Customer, Notification, WishlistItem


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "mobile", "city", "country", "created_at")
    search_fields = ("user__username", "user__email", "user__first_name", "user__last_name", "mobile")
    list_filter = ("city", "country", "created_at")


@admin.register(WishlistItem)
class WishlistItemAdmin(admin.ModelAdmin):
    list_display = ("user", "product", "created_at")
    search_fields = ("user__username", "product__name")
    list_select_related = ("user", "product")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "kind", "is_read", "created_at")
    list_filter = ("kind", "is_read", "created_at")
    search_fields = ("title", "message", "user__username")
    list_select_related = ("user",)
