import os
import hashlib
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

import requests

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from products.models import Product


class Command(BaseCommand):
    help = "Import up to 100 products from an authorized product feed"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        feed_url = os.environ.get("FLIPKART_FEED_URL")
        affiliate_id = os.environ.get("FLIPKART_AFFILIATE_ID")
        token = os.environ.get("FLIPKART_AFFILIATE_TOKEN")

        if not all([feed_url, affiliate_id, token]):
            raise CommandError(
                "Set FLIPKART_FEED_URL, FLIPKART_AFFILIATE_ID "
                "and FLIPKART_AFFILIATE_TOKEN first."
            )

        if urlparse(feed_url).scheme != "https":
            raise CommandError("Feed URL must use HTTPS.")

        session = requests.Session()
        session.headers.update({
            "Fk-Affiliate-Id": affiliate_id,
            "Fk-Affiliate-Token": token,
            "User-Agent": "FLIPKART-OG-Product-Importer/1.0",
        })

        response = session.get(feed_url, timeout=30)
        response.raise_for_status()
        payload = response.json()

        items = payload.get(
            "productInfoList",
            payload.get("products", [])
        )

        if not isinstance(items, list):
            raise CommandError("Unexpected product feed format.")

        imported = 0
        skipped = 0
        limit = max(1, min(options["limit"], 100))

        for item in items:
            if imported >= limit:
                break

            base = item.get("productBaseInfoV1", item)

            name = (
                base.get("title")
                or base.get("productName")
                or ""
            ).strip()

            description = (
                base.get("productDescription") or ""
            ).strip()

            price_data = (
                base.get("flipkartSellingPrice")
                or base.get("flipkartSpecialPrice")
                or base.get("sellingPrice")
                or base.get("price")
                or {}
            )

            if isinstance(price_data, dict):
                price_data = price_data.get("amount", 0)

            try:
                price = Decimal(str(price_data))
            except (InvalidOperation, TypeError):
                skipped += 1
                continue

            if not name or price <= 0:
                skipped += 1
                continue

            categories = str(
                item.get("categoryPaths", "")
            ).lower()

            if "mobile" in categories:
                category = "Mobiles"
            elif "electronic" in categories:
                category = "Electronics"
            elif any(x in categories for x in ("fashion", "clothing")):
                category = "Fashion"
            elif any(x in categories for x in ("home", "kitchen")):
                category = "Home"
            else:
                category = "Other"

            images = base.get("imageUrls") or {}
            image_url = ""

            if isinstance(images, dict):
                image_url = (
                    images.get("400x400")
                    or images.get("200x200")
                    or images.get("unknown")
                    or next(iter(images.values()), "")
                )
            elif isinstance(images, list) and images:
                image_url = (
                    images[0] if isinstance(images[0], str)
                    else images[0].get("url", "")
                )

            image_url = image_url or base.get("imageUrl", "")

            if not image_url.startswith("https://"):
                skipped += 1
                continue

            if Product.objects.filter(name=name).exists():
                skipped += 1
                continue

            if options["dry_run"]:
                self.stdout.write(f"Preview: {name} - Rs. {price}")
                imported += 1
                continue

            try:
                with transaction.atomic():
                    image_response = session.get(
                        image_url, timeout=20
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

                    digest = hashlib.sha256(
                        image_url.encode()
                    ).hexdigest()[:20]

                    product = Product(
                        name=name[:200],
                        category=category,
                        description=description,
                        price=price,
                        is_available=True,
                    )

                    product.image.save(
                        f"fk_{digest}{extension}",
                        ContentFile(image_response.content),
                        save=False,
                    )
                    product.save()

                imported += 1
                self.stdout.write(
                    self.style.SUCCESS(f"Imported: {name}")
                )

            except (requests.RequestException, OSError, ValueError) as exc:
                skipped += 1
                self.stderr.write(f"Skipped {name}: {exc}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Completed. Imported: {imported}; Skipped: {skipped}"
            )
        )