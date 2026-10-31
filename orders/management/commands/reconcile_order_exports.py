from django.core.management.base import BaseCommand, CommandError

from orders.services import WORKBOOK_PATH, reconcile_workbook


class Command(BaseCommand):
    help = "Retry the idempotent Excel export for all existing orders."

    def handle(self, *args, **options):
        if not WORKBOOK_PATH.exists():
            raise CommandError(f"Required workbook is missing: {WORKBOOK_PATH}")
        reconcile_workbook()
        self.stdout.write(self.style.SUCCESS(f"Reconciled order exports in {WORKBOOK_PATH}"))
