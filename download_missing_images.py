import os
import re
import requests
import django
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
from products.models import Product
from django.conf import settings

API = "https://dummyjson.com/products"
TARGETS = {"Electronics": ["laptops", "mobile-accessories"], "Mobiles": ["smartphones"]}
media_dir = Path(settings.MEDIA_ROOT) / "products"
media_dir.mkdir(parents=True, exist_ok=True)

session = requests.Session()
session.headers.update({"User-Agent": "FlipkartOG-Demo/1.0"})
api_items = []
for category, slugs in TARGETS.items():
    for slug in slugs:
        try:
            response = session.get(f"{API}/category/{slug}", timeout=20)
            response.raise_for_status()
            api_items.extend(response.json().get("products", []))
        except Exception as exc:
            print(f"API warning for {slug}: {exc}")

used_urls = set()
updated = 0
failed = []
for product in Product.objects.filter(image="", category__in=TARGETS).order_by("id"):
    name = product.name.lower()
    candidates = [x for x in api_items if x.get("thumbnail") or x.get("images")]
    keywords = [w for w in re.findall(r"[a-z0-9]+", name) if w not in {"demo", "edition", "series", "with", "and"}]
    def score(item):
        title = item.get("title", "").lower()
        return sum(1 for word in keywords if word in title)
    candidates.sort(key=score, reverse=True)
    chosen = next((x for x in candidates if score(x) > 0 and (x.get("thumbnail") or (x.get("images") or [None])[0]) not in used_urls), None)
    if not chosen:
        failed.append(product.name)
        continue
    url = chosen.get("thumbnail") or (chosen.get("images") or [None])[0]
    try:
        img = session.get(url, timeout=25)
        img.raise_for_status()
        content_type = img.headers.get("content-type", "")
        if not content_type.startswith("image/"):
            raise ValueError("URL did not return an image")
        ext = ".webp" if "webp" in content_type else ".png" if "png" in content_type else ".jpg"
        filename = f"product_{product.id}{ext}"
        (media_dir / filename).write_bytes(img.content)
        product.image.name = f"products/{filename}"
        product.save(update_fields=["image"])
        used_urls.add(url)
        updated += 1
        print(f"Saved: {product.name}")
    except Exception as exc:
        failed.append(f"{product.name}: {exc}")

print(f"\nImages added: {updated}")
print("Still missing:", Product.objects.filter(image="").count())
if failed:
    print("Products needing manual matching:")
    print("\n".join(failed))
