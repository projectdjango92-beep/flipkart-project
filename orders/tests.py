import json
from datetime import timedelta
from io import BytesIO

from openpyxl import load_workbook

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from customers.models import Address, Customer
from products.models import Product

from .models import Coupon, CouponRedemption, EMIPlan, Order, OrderItem
from .payments import upi_intent, upi_qr_code
from .services import WORKBOOK_PATH, generate_order_report


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

    def test_cod_and_eligible_emi_checkouts_remain_available(self):
        self.client.force_login(self.user)
        cod_response = self.client.post(reverse("cart"), data=json.dumps({
            "items": [{"product_id": self.product.pk, "quantity": 1}],
            "payment_method": "COD", "address_id": self.address.pk,
        }), content_type="application/json")
        self.assertEqual(cod_response.status_code, 200)
        cod_order = Order.objects.get()
        self.assertEqual(cod_order.payment_method, Order.PaymentMethod.COD)
        self.assertEqual(cod_order.payment_status, "PENDING")

        emi_plan = EMIPlan.objects.create(
            name="3-month plan", months=3, annual_interest_rate="12.00",
            minimum_purchase_amount="500.00",
        )
        emi_response = self.client.post(reverse("cart"), data=json.dumps({
            "items": [{"product_id": self.product.pk, "quantity": 1}],
            "payment_method": "EMI", "emi_plan_id": emi_plan.pk,
            "address_id": self.address.pk,
        }), content_type="application/json")
        self.assertEqual(emi_response.status_code, 200)
        emi_order = Order.objects.exclude(pk=cod_order.pk).get()
        self.assertEqual(emi_order.payment_method, Order.PaymentMethod.EMI)
        self.assertEqual(emi_order.emi_plan, emi_plan)

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

    def test_profile_avatar_opens_account_profile(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("index"))
        self.assertContains(response, 'class="profile-avatar"')
        self.assertContains(response, reverse("account_profile"))
        self.assertNotContains(response, "Hi, buyer")

    @override_settings(BHARAT_MART_UPI_ID="bharatmart@upi", BHARAT_MART_UPI_NAME="Bharat Mart")
    def test_online_upi_order_uses_server_total_and_stays_pending(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("cart"), data=json.dumps({
            "items": [{"product_id": self.product.pk, "quantity": 1, "price": "1.00"}],
            "payment_method": "ONLINE", "address_id": self.address.pk,
        }), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        order = Order.objects.get()
        self.assertEqual(order.payment_method, Order.PaymentMethod.ONLINE)
        self.assertEqual(order.payment_status, "PENDING")
        self.assertFalse(order.payment_successful)
        self.assertEqual(str(order.total_amount), "1000.00")
        self.assertEqual(response.json()["redirect_url"], reverse("upi_payment", args=[order.pk]))
        payment_page = self.client.get(response.json()["redirect_url"])
        self.assertContains(payment_page, "Open UPI app")
        self.assertContains(payment_page, "Payment pending verification")
        self.assertIn("am=1000.00", upi_intent(order))
        self.assertIn("tr=BM-", upi_intent(order))
        self.assertTrue(upi_qr_code(order).startswith("data:image/png;base64,"))
        self.client.force_login(self.other_user)
        self.assertEqual(self.client.get(reverse("upi_payment", args=[order.pk])).status_code, 404)


class OrderReportTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username="staff", password="safe-password-123", is_staff=True)
        user = User.objects.create_user(username="report-buyer", email="buyer@example.test")
        self.customer = Customer.objects.create(user=user, mobile="1", street="Road", address="Address", city="Mumbai", postcode="400001", country="India")
        self.product = Product.objects.create(name="Phone", category="Mobiles", price="1000.00", stock_quantity=5)
        self.order = Order.objects.create(customer=self.customer, subtotal_amount="1000.00", delivery_city="Mumbai", delivery_state="Maharashtra", delivery_pin_code="400001")
        OrderItem.objects.create(order=self.order, product=self.product, quantity=1, price="1000.00")

    def _workbook_from_response(self, response):
        return load_workbook(BytesIO(b"".join(response.streaming_content)))

    def test_download_is_staff_only(self):
        self.assertEqual(self.client.get(reverse("download_order_export")).status_code, 302)
        user = User.objects.create_user(username="not-staff", password="safe-password-123")
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("download_order_export")).status_code, 302)

    def test_report_is_fresh_and_preserves_template_layout(self):
        self.client.force_login(self.staff)
        template = load_workbook(WORKBOOK_PATH)
        response = self.client.get(reverse("download_order_export"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        workbook = self._workbook_from_response(response)
        orders_sheet, items_sheet = workbook["Orders"], workbook["Order Items"]
        self.assertEqual(orders_sheet.auto_filter.ref, "A1:P2")
        self.assertEqual(items_sheet.auto_filter.ref, "A1:G2")
        self.assertEqual(orders_sheet.freeze_panes, "A2")
        self.assertEqual(items_sheet.freeze_panes, "A2")
        self.assertEqual(orders_sheet.column_dimensions["A"].width, template["Orders"].column_dimensions["A"].width)
        self.assertEqual(orders_sheet.cell(2, 2).number_format, template["Orders"].cell(2, 2).number_format)
        self.assertEqual(orders_sheet.cell(2, 3).number_format, template["Orders"].cell(2, 3).number_format)
        self.assertEqual(orders_sheet.cell(2, 1).value, self.order.pk)
        self.assertEqual(items_sheet.cell(2, 1).value, self.order.pk)
        self.assertEqual(sum(row[0].value == self.order.pk for row in orders_sheet.iter_rows(min_row=2)), 1)
        self.assertEqual(sum(row[0].value == self.order.pk for row in items_sheet.iter_rows(min_row=2)), 1)

        later_order = Order.objects.create(customer=self.customer, subtotal_amount="1000.00")
        OrderItem.objects.create(order=later_order, product=self.product, quantity=1, price="1000.00")
        refreshed = load_workbook(generate_order_report())
        self.assertEqual(refreshed["Orders"].auto_filter.ref, "A1:P3")
        self.assertEqual(
            {row[0].value for row in refreshed["Orders"].iter_rows(min_row=2) if row[0].value},
            {self.order.pk, later_order.pk},
        )
        self.assertTrue(WORKBOOK_PATH.is_file())
