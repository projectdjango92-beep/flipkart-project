from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.db import models, transaction
from django.db.models import F, Q
from django.urls import reverse

from customers.models import Customer


class Coupon(models.Model):
    class DiscountType(models.TextChoices):
        PERCENTAGE = "PERCENTAGE", "Percentage"
        FIXED = "FIXED", "Fixed amount"
        FREE_DELIVERY = "FREE_DELIVERY", "Free delivery"

    code = models.CharField(max_length=40, unique=True)
    discount_type = models.CharField(max_length=20, choices=DiscountType.choices)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    minimum_order_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    maximum_discount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    starts_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    usage_limit = models.PositiveIntegerField(null=True, blank=True)
    per_user_limit = models.PositiveIntegerField(default=1)
    new_users_only = models.BooleanField(default=False)
    times_used = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("code",)

    def __str__(self):
        return self.code

    def discount_for(self, subtotal, delivery_charge):
        if self.discount_type == self.DiscountType.FREE_DELIVERY:
            return min(delivery_charge, subtotal)
        if self.discount_type == self.DiscountType.PERCENTAGE:
            amount = subtotal * self.discount_value / Decimal("100")
            if self.maximum_discount is not None:
                amount = min(amount, self.maximum_discount)
            return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return min(subtotal, self.discount_value)


class EMIPlan(models.Model):
    name = models.CharField(max_length=100)
    months = models.PositiveSmallIntegerField()
    annual_interest_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    processing_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    minimum_purchase_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    eligible_categories = models.CharField(max_length=200, blank=True, help_text="Comma-separated categories; blank means all.")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("months", "name")

    def __str__(self):
        return self.name

    def is_eligible_for(self, products, amount):
        allowed = {item.strip() for item in self.eligible_categories.split(",") if item.strip()}
        return amount >= self.minimum_purchase_amount and (not allowed or any(p.category in allowed for p in products))

    def installment(self, amount):
        amount = Decimal(amount) + self.processing_fee
        monthly_rate = Decimal(self.annual_interest_rate) / Decimal("1200")
        if not monthly_rate:
            return (amount / self.months).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        factor = (1 + monthly_rate) ** self.months
        return (amount * monthly_rate * factor / (factor - 1)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class Order(models.Model):
    class PaymentMethod(models.TextChoices):
        COD = "COD", "Cash on Delivery"
        ONLINE = "ONLINE", "Online payment"
        EMI = "EMI", "EMI (estimated)"
    class Status(models.TextChoices):
        PLACED = "PLACED", "Order Placed"
        CONFIRMED = "CONFIRMED", "Confirmed"
        PROCESSING = "PROCESSING", "Processing"
        SHIPPED = "SHIPPED", "Shipped"
        OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY", "Out for Delivery"
        DELIVERED = "DELIVERED", "Delivered"
        CANCELLED = "CANCELLED", "Cancelled"
        RETURN_REQUESTED = "RETURN_REQUESTED", "Return Requested"
        RETURN_APPROVED = "RETURN_APPROVED", "Return Approved"
        RETURN_REJECTED = "RETURN_REJECTED", "Return Rejected"

    class RefundStatus(models.TextChoices):
        NOT_APPLICABLE = "NOT_APPLICABLE", "Not applicable"
        NOT_PROCESSED = "NOT_PROCESSED", "Not processed"
        PENDING = "PENDING", "Pending manual processing"

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="orders")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    payment_successful = models.BooleanField(default=False)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.PLACED)
    cancellation_reason = models.TextField(blank=True)
    return_reason = models.TextField(blank=True)
    refund_status = models.CharField(max_length=24, choices=RefundStatus.choices, default=RefundStatus.NOT_APPLICABLE)
    stock_restored = models.BooleanField(default=False)
    payment_method = models.CharField(max_length=12, choices=PaymentMethod.choices, default=PaymentMethod.COD)
    payment_status = models.CharField(max_length=16, default="PENDING")
    coupon = models.ForeignKey(Coupon, null=True, blank=True, on_delete=models.SET_NULL, related_name="orders")
    subtotal_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    delivery_charge = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    coupon_discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    emi_plan = models.ForeignKey(EMIPlan, null=True, blank=True, on_delete=models.SET_NULL, related_name="orders")
    delivery_address_text = models.TextField(blank=True)
    delivery_city = models.CharField(max_length=100, blank=True)
    delivery_state = models.CharField(max_length=100, blank=True)
    delivery_pin_code = models.CharField(max_length=20, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["customer", "-created_at"]), models.Index(fields=["status"])]

    def __str__(self):
        return f"Order #{self.id}"

    @property
    def total_amount(self):
        return max(Decimal("0.00"), self.subtotal_amount + self.delivery_charge - self.coupon_discount)

    @property
    def delivery_status(self):
        return self.get_status_display()

    @property
    def can_cancel(self):
        return self.status in {self.Status.PLACED, self.Status.CONFIRMED, self.Status.PROCESSING}

    @property
    def can_request_return(self):
        return self.status == self.Status.DELIVERED

    def add_status_history(self, status=None, note=""):
        return OrderStatusHistory.objects.create(order=self, status=status or self.status, note=note)

    def _create_notification(self, title, message):
        from customers.models import Notification

        Notification.objects.create(
            user=self.customer.user,
            kind=Notification.Kind.ORDER,
            title=title,
            message=message,
            link=reverse("order_detail", kwargs={"pk": self.pk}),
        )

    def restore_stock(self):
        if self.stock_restored:
            return
        from products.models import Product

        with transaction.atomic():
            locked_order = Order.objects.select_for_update().get(pk=self.pk)
            if locked_order.stock_restored:
                return
            for item in locked_order.items.select_related("product"):
                product = Product.objects.select_for_update().get(pk=item.product_id)
                was_out_of_stock = not product.is_in_stock
                Product.objects.filter(pk=product.pk).update(stock_quantity=F("stock_quantity") + item.quantity)
                product.refresh_from_db(fields=["stock_quantity", "is_available"])
                if was_out_of_stock and product.is_in_stock:
                    from customers.models import Notification, WishlistItem

                    Notification.objects.bulk_create([
                        Notification(
                            user_id=wishlist_item.user_id,
                            kind=Notification.Kind.WISHLIST,
                            title=f"{product.name} is back in stock",
                            message="An item in your wishlist is available again.",
                            link=reverse("product_detail", kwargs={"pk": product.pk}),
                        )
                        for wishlist_item in WishlistItem.objects.filter(product=product)
                    ])
            locked_order.stock_restored = True
            locked_order.save(update_fields=["stock_restored", "updated_at"])
            self.stock_restored = True

    def transition_to(self, status, note=""):
        if status == self.status:
            return
        self.status = status
        self.save(update_fields=["status", "updated_at"])
        self.add_status_history(status, note)
        messages = {
            self.Status.CONFIRMED: ("Order confirmed", "Your order has been confirmed."),
            self.Status.PROCESSING: ("Order processing", "Your order is being prepared."),
            self.Status.SHIPPED: ("Order shipped", "Your order is on its way."),
            self.Status.OUT_FOR_DELIVERY: ("Out for delivery", "Your order is out for delivery."),
            self.Status.DELIVERED: ("Order delivered", "Your order has been delivered."),
            self.Status.CANCELLED: ("Order cancelled", "Your order was cancelled and stock was restored."),
            self.Status.RETURN_REQUESTED: ("Return requested", "Your return request has been received."),
            self.Status.RETURN_APPROVED: ("Return approved", "Your return was approved. No payment refund has been issued by this site."),
            self.Status.RETURN_REJECTED: ("Return request declined", "Your return request was not approved."),
        }
        if status in {self.Status.CANCELLED, self.Status.RETURN_APPROVED}:
            self.restore_stock()
        title, message = messages.get(status, ("Order updated", "Your order status was updated."))
        self._create_notification(title, message)


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("products.Product", on_delete=models.PROTECT, related_name="order_items")
    quantity = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gte=1), name="order_item_quantity_positive"),
            models.CheckConstraint(condition=Q(price__gte=0), name="order_item_price_nonnegative"),
        ]

    def __str__(self):
        return f"{self.product.name} × {self.quantity}"

    @property
    def subtotal(self):
        return self.price * self.quantity


class OrderStatusHistory(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="status_history")
    status = models.CharField(max_length=24, choices=Order.Status.choices)
    note = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"Order #{self.order_id}: {self.get_status_display()}"


class CouponRedemption(models.Model):
    coupon = models.ForeignKey(Coupon, on_delete=models.PROTECT, related_name="redemptions")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="coupon_redemption")
    created_at = models.DateTimeField(auto_now_add=True)
