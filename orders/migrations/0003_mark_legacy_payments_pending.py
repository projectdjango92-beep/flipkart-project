from django.db import migrations


def mark_legacy_payments_pending(apps, schema_editor):
    """The previous checkout marked every order paid without a payment gateway."""
    Order = apps.get_model("orders", "Order")
    Order.objects.update(payment_successful=False)


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0002_orderstatushistory_order_cancellation_reason_and_more"),
    ]

    operations = [
        migrations.RunPython(mark_legacy_payments_pending, migrations.RunPython.noop),
    ]
