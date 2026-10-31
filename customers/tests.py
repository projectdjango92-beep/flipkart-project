from django.contrib.auth.models import User
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from products.models import Product

from .models import Customer, WishlistItem


class WishlistTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="wish-user", password="safe-password-123")
        self.other_user = User.objects.create_user(username="other-user", password="safe-password-123")
        self.product = Product.objects.create(name="Lamp", category="Home", price="799.00", stock_quantity=2)

    def test_wishlist_requires_login_and_is_unique_per_user(self):
        response = self.client.post(reverse("wishlist_toggle", args=[self.product.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)
        self.client.force_login(self.user)
        self.client.post(reverse("wishlist_toggle", args=[self.product.pk]))
        self.assertEqual(WishlistItem.objects.filter(user=self.user, product=self.product).count(), 1)
        with self.assertRaises(IntegrityError):
            WishlistItem.objects.create(user=self.user, product=self.product)

    def test_user_cannot_remove_another_users_wishlist_item(self):
        item = WishlistItem.objects.create(user=self.user, product=self.product)
        self.client.force_login(self.other_user)
        response = self.client.post(reverse("wishlist_remove", args=[item.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(WishlistItem.objects.filter(pk=item.pk).exists())


class AccountJourneyTests(TestCase):
    def test_registration_login_and_profile_pages(self):
        registration_data = {
            "first_name": "Test",
            "last_name": "Shopper",
            "email": "shopper@example.com",
            "username": "test-shopper",
            "password": "Unique-safe-password-123",
            "password_confirm": "Unique-safe-password-123",
            "mobile": "9999999999",
            "street": "Market Road",
            "address": "12 Market Road",
            "city": "Mumbai",
            "postcode": "400001",
            "country": "India",
        }
        response = self.client.post(reverse("register"), registration_data)
        self.assertRedirects(response, reverse("index"))
        self.assertTrue(Customer.objects.filter(user__username="test-shopper").exists())
        self.assertEqual(self.client.get(reverse("account_profile")).status_code, 200)

        self.client.logout()
        response = self.client.post(
            reverse("login"),
            {"username": "test-shopper", "password": "Unique-safe-password-123"},
        )
        self.assertRedirects(response, reverse("index"))
