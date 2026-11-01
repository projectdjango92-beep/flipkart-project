from django.contrib import admin

from .models import Coupon, CouponRedemption, EMIPlan, Order, OrderItem, OrderStatusHistory

admin.site.register(Coupon)
admin.site.register(EMIPlan)
admin.site.register(CouponRedemption)


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    fields = ("product", "quantity", "price", "subtotal_display")
    readonly_fields = ("product", "quantity", "price", "subtotal_display")

    @admin.display(description="Subtotal")
    def subtotal_display(self, obj):
        return obj.subtotal if obj.pk else "-"


class OrderStatusHistoryInline(admin.TabularInline):
    model = OrderStatusHistory
    extra = 0
    can_delete = False
    fields = ("status", "note", "created_at")
    readonly_fields = ("status", "note", "created_at")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    actions = ("retry_excel_export",)
    list_display = ("id", "customer", "status", "payment_method", "payment_status", "payment_successful", "total_amount_display", "created_at")
    list_filter = ("status", "payment_successful", "refund_status", "created_at")
    search_fields = ("id", "customer__user__username", "customer__user__email")
    readonly_fields = ("created_at", "updated_at", "stock_restored", "total_amount_display")
    fields = ("customer", "status", "payment_method", "payment_status", "payment_successful", "coupon", "subtotal_amount", "delivery_charge", "coupon_discount", "emi_plan", "refund_status", "cancellation_reason", "return_reason", "stock_restored", "created_at", "updated_at", "total_amount_display")
    inlines = (OrderItemInline, OrderStatusHistoryInline)
    ordering = ("-created_at",)
    list_per_page = 25

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("customer", "customer__user").prefetch_related("items")

    @admin.display(description="Total Amount")
    def total_amount_display(self, obj):
        return obj.total_amount

    def save_model(self, request, obj, form, change):
        if not change:
            super().save_model(request, obj, form, change)
            obj.add_status_history(obj.status, "Created in admin")
            return
        previous = Order.objects.get(pk=obj.pk)
        desired_status = obj.status
        if desired_status != previous.status:
            obj.status = previous.status
        super().save_model(request, obj, form, change)
        if desired_status != previous.status:
            obj.transition_to(desired_status, f"Updated by {request.user.get_username()} in admin")

    @admin.action(description="Mark selected orders for the next Excel download")
    def retry_excel_export(self, request, queryset):
        from .services import export_order_after_commit
        for order in queryset:
            export_order_after_commit(order.pk)
        self.message_user(request, "The Excel report is generated from the database when an authorized staff member downloads it.")


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("order", "product", "quantity", "price", "subtotal_display")
    search_fields = ("order__id", "product__name")
    readonly_fields = ("order", "product", "quantity", "price", "subtotal_display")

    @admin.display(description="Subtotal")
    def subtotal_display(self, obj):
        return obj.subtotal
