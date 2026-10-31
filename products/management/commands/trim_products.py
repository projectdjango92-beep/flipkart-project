from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count
from products.models import Product

class Command(BaseCommand):
    help = "Keep exactly 25 products in each target category while preserving ordered products"

    def handle(self, *args, **options):
        categories = ["Electronics", "Mobiles", "Fashion", "Home"]
        with transaction.atomic():
            for category in categories:
                products = list(Product.objects.filter(category=category).annotate(order_count=Count("order_items", distinct=True)).order_by("id"))
                ordered = [p for p in products if p.order_count > 0]
                if len(ordered) > 25:
                    raise Exception(f"{category} has more than 25 order-linked products; nothing was changed.")
                keep_ids = {p.id for p in ordered}
                for product in products:
                    if len(keep_ids) >= 25:
                        break
                    keep_ids.add(product.id)
                if len(products) < 25:
                    raise Exception(f"{category} has fewer than 25 products; nothing was changed.")
                Product.objects.filter(category=category).exclude(id__in=keep_ids).delete()
                self.stdout.write(f"{category}: {Product.objects.filter(category=category).count()} products")
        total = Product.objects.filter(category__in=categories).count()
        self.stdout.write(self.style.SUCCESS(f"FINAL TOTAL: {total}"))
