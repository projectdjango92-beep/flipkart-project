"""Load the checked-in product catalogue without replacing live data."""

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from products.models import Product, ProductImage


CATALOGUE_PATH = Path(settings.BASE_DIR) / "products" / "fixtures" / "catalogue.json"
PRODUCT_FIELDS = (
    "name",
    "category",
    "brand",
    "sku",
    "description",
    "price",
    "image",
    "is_available",
    "stock_quantity",
    "low_stock_threshold",
)


class Command(BaseCommand):
    help = "Create missing catalogue products from the checked-in local database export."

    def _read_catalogue(self):
        try:
            with CATALOGUE_PATH.open(encoding="utf-8") as catalogue_file:
                return json.load(catalogue_file)
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(f"Could not read catalogue fixture: {exc}") from exc

    def _validate_images(self, records):
        image_names = [
            record["fields"].get("image")
            for record in records
            if record["model"] in {"products.product", "products.productimage"}
        ]
        missing = [
            image_name
            for image_name in image_names
            if image_name and not (Path(settings.MEDIA_ROOT) / image_name).is_file()
        ]
        if missing:
            preview = ", ".join(missing[:5])
            raise CommandError(
                "Catalogue media files are missing; no database changes were made: "
                f"{preview}"
            )

    def handle(self, *args, **options):
        records = self._read_catalogue()
        self._validate_images(records)
        source_to_product = {}
        products_created = images_created = 0

        with transaction.atomic():
            for record in records:
                if record["model"] != "products.product":
                    continue

                fields = record["fields"]
                sku = fields.get("sku")
                if sku:
                    product = Product.objects.filter(sku=sku).first()
                else:
                    # A few legacy products have no SKU. Their category and image
                    # path make a stable import key without changing the model.
                    product = Product.objects.filter(
                        name=fields["name"],
                        category=fields["category"],
                        image=fields.get("image") or "",
                    ).first()

                if product is None:
                    defaults = {field: fields.get(field) for field in PRODUCT_FIELDS}
                    product = Product.objects.create(**defaults)
                    products_created += 1
                source_to_product[record["pk"]] = product

            for record in records:
                if record["model"] != "products.productimage":
                    continue

                fields = record["fields"]
                product = source_to_product.get(fields["product"])
                if product is None:
                    raise CommandError("Catalogue gallery image refers to an unknown product.")
                _, created = ProductImage.objects.get_or_create(
                    product=product,
                    image=fields["image"],
                    defaults={
                        "alt_text": fields.get("alt_text", ""),
                        "sort_order": fields.get("sort_order", 0),
                    },
                )
                images_created += int(created)

        self.stdout.write(
            self.style.SUCCESS(
                "Catalogue seed complete: "
                f"{products_created} products and {images_created} gallery images created."
            )
        )
