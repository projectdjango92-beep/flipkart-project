"""Copy existing local media to Cloudinary without changing database records."""

from pathlib import Path

import cloudinary.api
import cloudinary.uploader
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from products.models import Product, ProductImage


class Command(BaseCommand):
    help = (
        "Copy MEDIA_ROOT files to Cloudinary using their existing relative names, "
        "then verify every remote asset. Does not modify database rows or local files."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report the files that would be copied without contacting Cloudinary.",
        )

    @staticmethod
    def public_id(relative_name: str) -> str:
        """Cloudinary public IDs omit the filename extension but retain folders."""
        return Path(relative_name).with_suffix("").as_posix()

    @staticmethod
    def remote_asset(public_id: str):
        try:
            return cloudinary.api.resource(public_id, resource_type="image")
        except Exception as exc:  # Cloudinary returns an exception for an absent asset.
            if "not found" in str(exc).lower():
                return None
            raise

    def handle(self, *args, **options):
        if not settings.CLOUDINARY_ENABLED:
            raise CommandError(
                "Cloudinary is not configured. Set all three CLOUDINARY_* variables first."
            )

        media_root = Path(settings.MEDIA_ROOT)
        files = sorted(path for path in media_root.rglob("*") if path.is_file())
        if not files:
            raise CommandError(f"No media files found in {media_root}.")

        if options["dry_run"]:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Dry run: {len(files)} files would be copied; no network or database changes made."
                )
            )
            return

        uploaded = 0
        already_present = 0
        for source in files:
            relative_name = source.relative_to(media_root).as_posix()
            public_id = self.public_id(relative_name)
            remote = self.remote_asset(public_id)
            if remote is None:
                cloudinary.uploader.upload(
                    str(source),
                    resource_type="image",
                    public_id=public_id,
                    overwrite=False,
                    unique_filename=False,
                    use_filename=False,
                )
                uploaded += 1
                remote = self.remote_asset(public_id)
            else:
                already_present += 1

            if remote is None or remote.get("bytes") != source.stat().st_size:
                raise CommandError(
                    f"Verification failed for {relative_name}; local files and database were not changed."
                )

        field_names = list(Product.objects.exclude(image="").values_list("image", flat=True))
        field_names.extend(ProductImage.objects.values_list("image", flat=True))
        missing_references = [
            name for name in field_names if self.remote_asset(self.public_id(name)) is None
        ]
        if missing_references:
            raise CommandError(
                f"{len(missing_references)} database image references are absent from Cloudinary."
            )

        self.stdout.write(
            self.style.SUCCESS(
                "Cloudinary media migration verified: "
                f"files={len(files)}, uploaded={uploaded}, already_present={already_present}, "
                f"product_images={len(field_names) - ProductImage.objects.count()}, "
                f"gallery_images={ProductImage.objects.count()}."
            )
        )
