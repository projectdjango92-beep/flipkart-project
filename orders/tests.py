import json
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from customers.models import Address, Customer
from products.models import Product

from .models import Coupon, CouponRedemption, Order


class CheckoutAndOrderSecurityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="buyer", password="safe-password-123")
        self.customer = Customer.objects.create(user=self.user, mobile="1", street="Road", address="Address", city="Mumbai", postcode="400001", country="India")
        self.other_user = User.objects.create_user(username="other", password="safe-password-123")
        Customer.objects.create(user=self.other_user, mobile="2", street="Road", address="Address", city="Pune", postcode="411001", country="India")
        self.product = Product.objects.create(name="Phone", category="Mobiles", price="1000.00", stock_quantity=2)
        self.address = Address.objects.create(customer=self.customer, full_name="Buyer", mobile="1", house="1", street="Road", city="Mumbai", state="Maharashtra", pin_code="400001", is_default=True)

    def test_checkout_uses_database_price_and_decrements_stock(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("cart"), data=json.dumps({"items": [{"product_id": self.product.pk, "quantity": 2, "price": "1.00"}], "address_id": self.address.pk}), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.product.refresh_from_db()
        order = Order.objects.get()
        self.assertEqual(self.product.stock_quantity, 0)
        self.assertEqual(str(order.items.get().price), "1000.00")
        self.assertFalse(order.payment_successful)
        self.assertEqual(order.status, Order.Status.PLACED)

    def test_cancellation_restores_stock_once_and_orders_are_private(self):
        self.client.force_login(self.user)
        self.client.post(reverse("cart"), data=json.dumps({"items": [{"product_id": self.product.pk, "quantity": 1}], "address_id": self.address.pk}), content_type="application/json")
        order = Order.objects.get()
        response = self.client.post(reverse("order_cancel", args=[order.pk]), {"reason": "Changed my mind"})
        self.assertRedirects(response, reverse("order_detail", args=[order.pk]))
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 2)
        self.assertTrue(order.status_history.filter(status=Order.Status.CANCELLED).exists())
        self.assertEqual(self.client.get(reverse("order_detail", args=[order.pk])).status_code, 200)
        self.client.force_login(self.other_user)
        self.assertEqual(self.client.get(reverse("order_detail", args=[order.pk])).status_code, 404)

    def test_valid_new_user_coupon_is_calculated_on_the_server(self):
        coupon = Coupon.objects.create(
            code="WELCOME10", discount_type=Coupon.DiscountType.PERCENTAGE,
            discount_value="10.00", maximum_discount="150.00", starts_at=timezone.now() - timedelta(days=1),
            expires_at=timezone.now() + timedelta(days=1), new_users_only=True,
        )
        self.client.force_login(self.user)
        response = self.client.post(reverse("cart"), data=json.dumps({
            "items": [{"product_id": self.product.pk, "quantity": 1}], "coupon_code": "welcome10", "address_id": self.address.pk,
        }), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        order = Order.objects.get()
        self.assertEqual(str(order.coupon_discount), "100.00")
        self.assertEqual(order.coupon, coupon)
        self.assertTrue(CouponRedemption.objects.filter(order=order, coupon=coupon).exists())
