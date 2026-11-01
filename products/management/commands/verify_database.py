"""Read-only safety checks for a configured database."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from customers.models import Customer
from orders.models import Order, OrderItem
from products.models import Product, ProductImage


class Command(BaseCommand):
    help = "Verify the configured database connection and optional empty import target."

    def add_arguments(self, parser):
        parser.add_argument(
            "--require-postgresql",
            action="store_true",
            help="Fail unless DATABASE_URL selected PostgreSQL.",
        )
        parser.add_argument(
            "--require-empty-business-data",
            action="store_true",
            help="Fail when users, catalogue, customers, orders, or order items exist.",
        )

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()

        vendor = connection.vendor
        if options["require_postgresql"] and vendor != "postgresql":
            raise CommandError("PostgreSQL is not active. Set DATABASE_URL before continuing.")

        # A new Neon database has no tables before `migrate`. Introspection
        # lets this command prove its connection and safely report that state
        # without treating the missing schema as an application error.
        table_names = set(connection.introspection.table_names())
        models = {
            "users": get_user_model(),
            "customers": Customer,
            "products": Product,
            "gallery_images": ProductImage,
            "orders": Order,
            "order_items": OrderItem,
        }
        counts = {
            name: model.objects.count() if model._meta.db_table in table_names else 0
            for name, model in models.items()
        }
        if options["require_empty_business_data"] and any(counts.values()):
            raise CommandError(
                "Target contains business data; refusing an import that could overwrite or duplicate it."
            )

        self.stdout.write(self.style.SUCCESS(f"Database connection verified ({vendor})."))
        self.stdout.write("Business-record counts: " + ", ".join(
            f"{name}={count}" for name, count in counts.items()
        ))
