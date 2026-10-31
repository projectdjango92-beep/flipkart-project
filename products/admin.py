from django.contrib import admin
from django.db.models import F
from import_export.admin import ImportExportModelAdmin

from .models import Product, ProductImage, Review
from .resources import ProductResource


class LowStockFilter(admin.SimpleListFilter):
    title = "inventory"
    parameter_name = "inventory"

    def lookups(self, request, model_admin):
        return (("low", "Low stock"), ("out", "Out of stock"))

    def queryset(self, request, queryset):
        if self.value() == "low":
            return queryset.filter(stock_quantity__gt=0, stock_quantity__lte=F("low_stock_threshold"))
        if self.value() == "out":
            return queryset.filter(stock_quantity=0)
        return queryset


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ("image", "alt_text", "sort_order")


@admin.register(Product)
class ProductAdmin(ImportExportModelAdmin):
    resource_class = ProductResource
    list_display = ("id", "name", "brand", "category", "price", "stock_quantity", "low_stock_threshold", "is_available", "created_at")
    list_editable = ("stock_quantity", "low_stock_threshold", "is_available")
    list_filter = ("category", "is_available", LowStockFilter)
    search_fields = ("name", "brand", "sku", "description")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "updated_at")
    inlines = (ProductImageInline,)


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("product", "user", "rating", "verified_purchase", "created_at")
    list_filter = ("rating", "verified_purchase", "created_at")
    search_fields = ("product__name", "user__username", "comment")
    readonly_fields = ("created_at", "updated_at")
