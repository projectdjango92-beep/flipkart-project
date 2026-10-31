
import requests

from decimal import Decimal
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from products.models import Product


CATEGORY_MAP = {
    "laptops": "Electronics",
    "tablets": "Electronics",
    "smartphones": "Mobiles",
    "mobile-accessories": "Mobiles",
    "mens-shirts": "Fashion",
    "mens-shoes": "Fashion",
    "womens-dresses": "Fashion",
    "womens-shoes": "Fashion",
    "womens-bags": "Fashion",
    "womens-jewellery": "Fashion",
    "tops": "Fashion",
    "sunglasses": "Fashion",
    "beauty": "Fashion",
    "skin-care": "Fashion",
    "fragrances": "Fashion",
    "sports-accessories": "Fashion",
    "furniture": "Home",
    "home-decoration": "Home",
    "kitchen-accessories": "Home",
}

ALLOWED_CATEGORIES = {"Electronics", "Mobiles", "Fashion", "Home"}


class Command(BaseCommand):
    help = "Import demo products into the four supported categories"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        limit = max(1, min(options["limit"], 100))

        try:
            response = requests.get(
                "https://dummyjson.com/products",
                params={"limit": limit, "skip": 0},
                timeout=30,
            )
            response.raise_for_status()
            items = response.json()["products"]
        except (requests.RequestException, ValueError, KeyError) as exc:
            raise CommandError(f"Could not retrieve products: {exc}")

        prepared = []

        for item in items:
            category = CATEGORY_MAP.get(
                str(item.get("category", "")).lower()
            )

            # Ignore categories that do not belong to the four allowed ones.
            if category not in ALLOWED_CATEGORIES:
                continue

            name = str(item.get("title", "")).strip()
            image_url = item.get("thumbnail") or (
                item.get("images") or [None]
            )[0]

            try:
                price = Decimal(str(item["price"]))
            except (KeyError, ValueError, TypeError):
                continue

            if (
                not name
                or price <= 0
                or not image_url
                or not image_url.startswith("https://")
            ):
                continue

            prepared.append({
                "id": item["id"],
                "name": name[:200],
                "sku": str(item.get("sku") or f"DEMO-{item['id']}"),
                "category": category,
                "brand": str(item.get("brand") or "Sample")[:100],
                "description": str(item.get("description") or ""),
                "price": price,
                "stock": max(0, int(item.get("stock", 0))),
                "image_url": image_url,
            })

        if options["dry_run"]:
            for product in prepared:
                self.stdout.write(
                    f"{product['category']} | {product['name']} "
                    f"| Rs. {product['price']}"
                )

            self.stdout.write(
                f"Preview only: {len(prepared)} supported products. "
                "Nothing changed."
            )
            return

        imported = 0
        skipped = 0

        for product_data in prepared:
            if Product.objects.filter(sku=product_data["sku"]).exists():
                skipped += 1
                continue

            try:
                image_response = requests.get(
                    product_data["image_url"],
                    timeout=20,
                )
                image_response.raise_for_status()

                content_type = image_response.headers.get(
                    "Content-Type", ""
                ).split(";")[0].lower()

                extensions = {
                    "image/jpeg": ".jpg",
                    "image/png": ".png",
                    "image/webp": ".webp",
                }
                extension = extensions.get(content_type)

                if not extension:
                    skipped += 1
                    continue

                with transaction.atomic():
                    product = Product(
                        name=product_data["name"],
                        category=product_data["category"],
                        brand=product_data["brand"],
                        sku=product_data["sku"],
                        description=product_data["description"],
                        price=product_data["price"],
                        is_available=True,
                        stock_quantity=product_data["stock"],
                        low_stock_threshold=5,
                    )

                    product.image.save(
                        f"demo_{product_data['id']}{extension}",
                        ContentFile(image_response.content),
                        save=False,
                    )
                    product.save()

                imported += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Imported [{product_data['category']}]: "
                        f"{product_data['name']}"
                    )
                )

            except (
                requests.RequestException,
                ValueError,
                TypeError,
                OSError,
            ) as exc:
                skipped += 1
                self.stderr.write(
                    f"Skipped {product_data['name']}: {exc}"
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Finished. Imported: {imported}; skipped: {skipped}."
            )
        )
