from django.core.management.base import BaseCommand
from products.models import Product

class Command(BaseCommand):
    help = "Fill categories to at least 25 demo products each"

    def handle(self, *args, **options):
        items = {"Electronics": ["Laptop", "Gaming Monitor", "Mechanical Keyboard", "Wireless Mouse", "Bluetooth Speaker", "Smart TV", "Webcam", "Printer", "Router", "External SSD", "Headphones", "Gaming Console", "Graphics Tablet", "Projector", "USB Hub", "Microphone", "Soundbar", "Power Bank", "Smart Watch", "Camera", "Tripod", "Desktop PC", "Gaming Headset", "WiFi Extender", "Portable SSD"], "Mobiles": ["Samsung Galaxy", "Apple iPhone", "OnePlus Nord", "Google Pixel", "Redmi Note", "Realme Narzo", "Vivo V Series", "Oppo Reno", "Motorola Edge", "Nothing Phone", "Poco X Series", "iQOO Neo", "Infinix Note", "Tecno Camon", "Honor X Series", "Nokia G Series", "Asus ROG Phone", "Samsung Galaxy A", "Apple iPhone Plus", "OnePlus Flagship", "Redmi K Series", "Realme GT", "Vivo Y Series", "Oppo A Series", "Motorola G Series"]}
        for category, names in items.items():
            existing = Product.objects.filter(category=category).count()
            for i, name in enumerate(names, 1):
                if existing >= 25:
                    break
                sku = f"FILL-{category[:3].upper()}-{i:03d}"
                product, created = Product.objects.get_or_create(sku=sku, defaults={"name": name + " Demo Edition", "category": category, "brand": "Demo", "price": 999 + i * 100, "description": "Sample catalogue product. Not a live retail listing.", "stock_quantity": 20, "is_available": True})
                if created:
                    existing += 1
            self.stdout.write(f"{category}: {Product.objects.filter(category=category).count()}")
