from django.core.management.base import BaseCommand
from django.db import transaction
from products.models import Product


class Command(BaseCommand):
    help = "Balance the catalogue to 25 products in each of four categories"

    def handle(self, *args, **options):
        categories = ["Electronics", "Mobiles", "Fashion", "Home"]
        with transaction.atomic():
            for category in categories:
                products = list(Product.objects.filter(category=category).order_by("id"))
                if len(products) > 25:
                    for product in products[25:]:
                        product.delete()
                self.stdout.write(f"{category}: {min^(len^(products^), 25^)} existing products checked")
        self.stdout.write(self.style.WARNING("This command only trims categories above 25; it does not add missing products."))
