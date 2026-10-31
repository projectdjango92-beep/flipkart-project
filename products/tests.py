from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from customers.models import Customer
from orders.models import Order, OrderItem

from .models import Product, ProductImage, Review


class CatalogueSeedTests(TestCase):
    def test_catalogue_seed_is_repeatable(self):
        self.assertFalse(Product.objects.exists())

        call_command("seed_catalogue")
        first_product_count = Product.objects.count()
        first_image_count = ProductImage.objects.count()

        call_command("seed_catalogue")
        self.assertEqual(Product.objects.count(), first_product_count)
        self.assertEqual(ProductImage.objects.count(), first_image_count)
        self.assertEqual(first_product_count, 100)
        self.assertEqual(first_image_count, 9)


class ReviewAccessTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="buyer", password="safe-password-123")
        self.customer = Customer.objects.create(user=self.user, mobile="1", street="Road", address="Address", city="Mumbai", postcode="400001", country="India")
        self.product = Product.objects.create(
            name="Headphones",
            category="Electronics",
            price="999.00",
            image="products/demo_1.webp",
            stock_quantity=5,
        )

    def test_customer_cannot_review_before_purchase(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("review_create", args=[self.product.pk]), {"rating": 5, "comment": "Nice"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Review.objects.exists())

    def test_catalogue_filter_and_product_page_render(self):
        response = self.client.get(reverse("index"), {"q": "head", "category": "Electronics", "rating": "1", "sort": "rating"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Headphones")
        self.assertEqual(self.client.get(reverse("product_detail", args=[self.product.pk])).status_code, 200)

    def test_purchaser_can_submit_one_verified_review(self):
        order = Order.objects.create(customer=self.customer)
        OrderItem.objects.create(order=order, product=self.product, quantity=1, price=self.product.price)
        self.client.force_login(self.user)
        response = self.client.post(reverse("review_create", args=[self.product.pk]), {"rating": 5, "comment": "Nice"})
        self.assertRedirects(response, reverse("product_detail", args=[self.product.pk]))
        review = Review.objects.get()
        self.assertTrue(review.verified_purchase)
        with self.assertRaises(IntegrityError):
            Review.objects.create(product=self.product, user=self.user, rating=4)
