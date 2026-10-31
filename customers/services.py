from .models import Customer


def get_or_create_customer(user):
    """Repair legacy authenticated users without inventing delivery information."""
    customer, _ = Customer.objects.get_or_create(
        user=user,
        defaults={"mobile": "", "street": "", "address": "", "city": "", "postcode": "", "country": ""},
    )
    return customer
