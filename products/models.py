
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q


class Product(models.Model):
    CATEGORY_CHOICES = (
        ("Electronics", "Electronics"),
        ("Mobiles", "Mobiles"),
        ("Fashion", "Fashion"),
        ("Home", "Home"),
    )

    name = models.CharField(max_length=200)
    category = models.CharField(max_length=100, choices=CATEGORY_CHOICES)
    brand = models.CharField(max_length=100, blank=True)
    sku = models.CharField(max_length=64, blank=True, null=True, unique=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    image = models.ImageField(upload_to="products/", blank=True, null=True)
    is_available = models.BooleanField(default=True)
    stock_quantity = models.PositiveIntegerField(default=20)
    low_stock_threshold = models.PositiveIntegerField(default=5)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(stock_quantity__gte=0),
                name="product_stock_quantity_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(low_stock_threshold__gte=0),
                name="product_low_stock_threshold_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(price__gte=Decimal("0.00")),
                name="product_price_nonnegative",
            ),
        ]
        indexes = [models.Index(fields=["category", "is_available"])]

    def __str__(self):
        return self.name

    @property
    def is_in_stock(self):
        return self.is_available and self.stock_quantity > 0

    @property
    def is_low_stock(self):
        return self.is_in_stock and self.stock_quantity <= self.low_stock_threshold

    @property
    def availability_label(self):
        if not self.is_available or self.stock_quantity == 0:
            return "Out of stock"
        if self.is_low_stock:
            return f"Only {self.stock_quantity} left"
        return "In stock"

    @property
    def average_rating(self):
        if hasattr(self, "rating_average"):
            return self.rating_average
        return self.reviews.aggregate(value=models.Avg("rating"))["value"] or Decimal("0")

    @property
    def total_reviews(self):
        if hasattr(self, "review_count"):
            return self.review_count
        return self.reviews.count()


class ProductImage(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="images"
    )
    image = models.ImageField(upload_to="products/gallery/")
    alt_text = models.CharField(max_length=160, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"{self.product.name} image"


class Review(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="reviews"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="product_reviews",
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comment = models.TextField(max_length=2000, blank=True)
    verified_purchase = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "user"],
                name="one_review_per_user_product",
            ),
            models.CheckConstraint(
                condition=Q(rating__gte=1) & Q(rating__lte=5),
                name="review_rating_between_one_and_five",
            ),
        ]
        indexes = [models.Index(fields=["product", "-created_at"])]

    def __str__(self):
        return f"{self.product} review by {self.user}"
