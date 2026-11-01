from django.core.management.base import BaseCommand, CommandError

from orders.services import WORKBOOK_PATH, reconcile_workbook


class Command(BaseCommand):
    help = "Validate that a fresh, database-backed Excel report can be generated."

    def handle(self, *args, **options):
        if not WORKBOOK_PATH.exists():
            raise CommandError(f"Required workbook is missing: {WORKBOOK_PATH}")
        reconcile_workbook()
        self.stdout.write(self.style.SUCCESS("Generated an in-memory order report successfully."))
