"""Copy existing local media to Cloudinary without changing database records."""

import socket
import time
from pathlib import Path

import cloudinary.api
import cloudinary.uploader
from cloudinary.exceptions import GeneralError, RateLimited
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from products.models import Product, ProductImage


class Command(BaseCommand):
    help = (
        "Copy MEDIA_ROOT files to Cloudinary using their existing relative names, "
        "then verify every remote asset. Does not modify database rows or local files."
    )
    REQUEST_TIMEOUT_SECONDS = 20
    MAX_ATTEMPTS = 4
    RETRY_DELAY_SECONDS = 1

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

    def call_with_retry(self, action, operation):
        """Run a bounded Cloudinary request; never wait indefinitely."""
        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            try:
                return operation()
            except Exception as exc:
                transient_text = str(exc).lower()
                is_transient = isinstance(
                    exc, (RateLimited, GeneralError, socket.timeout, TimeoutError)
                ) or any(
                    marker in transient_text
                    for marker in ("timeout", "temporar", "rate limit", "error 500", "error 502", "error 503", "error 504")
                )
                if not is_transient:
                    raise CommandError(
                        f"{action} failed ({exc.__class__.__name__}). Stopped safely."
                    ) from exc
                if attempt == self.MAX_ATTEMPTS:
                    raise CommandError(
                        f"{action} failed after {attempt} attempts ({exc.__class__.__name__}). "
                        "Stopped safely; rerun the command to resume."
                    ) from exc
                delay = self.RETRY_DELAY_SECONDS * (2 ** (attempt - 1))
                self.stdout.write(
                    self.style.WARNING(
                        f"{action}: temporary {exc.__class__.__name__}; retrying in {delay}s "
                        f"({attempt}/{self.MAX_ATTEMPTS})."
                    )
                )
                time.sleep(delay)

    def existing_assets(self, files, media_root):
        """Get the remote inventory in pages, avoiding one Admin API call per file."""
        remote_assets = {}
        prefixes = sorted({path.relative_to(media_root).parts[0] for path in files})
        for prefix in prefixes:
            cursor = None
            while True:
                page = self.call_with_retry(
                    f"Cloudinary inventory request for {prefix}",
                    lambda: cloudinary.api.resources(
                        resource_type="image",
                        type="upload",
                        prefix=f"{prefix}/",
                        max_results=500,
                        next_cursor=cursor,
                        timeout=self.REQUEST_TIMEOUT_SECONDS,
                    ),
                )
                for asset in page.get("resources", []):
                    remote_assets[asset["public_id"]] = asset
                cursor = page.get("next_cursor")
                if not cursor:
                    break
        return remote_assets

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

        remote_assets = self.existing_assets(files, media_root)
        uploaded = skipped = verified = failed = 0
        for index, source in enumerate(files, start=1):
            relative_name = source.relative_to(media_root).as_posix()
            public_id = self.public_id(relative_name)
            remote = remote_assets.get(public_id)
            progress = f"[{index}/{len(files)}] {relative_name}"
            if remote is not None:
                skipped += 1
                status = "skipped"
            else:
                self.stdout.write(f"{progress} uploading")
                try:
                    remote = self.call_with_retry(
                        f"Upload for {relative_name}",
                        lambda: cloudinary.uploader.upload(
                            str(source),
                            resource_type="image",
                            public_id=public_id,
                            overwrite=False,
                            unique_filename=False,
                            use_filename=False,
                            timeout=self.REQUEST_TIMEOUT_SECONDS,
                        ),
                    )
                except CommandError as exc:
                    failed += 1
                    self.stdout.write(self.style.ERROR(f"{progress} failed"))
                    raise CommandError(
                        f"Migration stopped: uploaded={uploaded}, skipped={skipped}, "
                        f"verified={verified}, failed={failed}. {exc}"
                    ) from exc
                remote_assets[public_id] = remote
                uploaded += 1
                status = "uploaded"

            if remote.get("bytes") != source.stat().st_size:
                failed += 1
                self.stdout.write(self.style.ERROR(f"{progress} failed size verification"))
                raise CommandError(
                    f"Migration stopped: uploaded={uploaded}, skipped={skipped}, "
                    f"verified={verified}, failed={failed}. Remote size did not match for "
                    f"{relative_name}; local files and database were not changed."
                )
            verified += 1
            self.stdout.write(self.style.SUCCESS(f"{progress} {status} and verified"))

        field_names = list(Product.objects.exclude(image="").values_list("image", flat=True))
        field_names.extend(ProductImage.objects.values_list("image", flat=True))
        missing_references = [name for name in field_names if self.public_id(name) not in remote_assets]
        if missing_references:
            raise CommandError(
                f"{len(missing_references)} database image references are absent from Cloudinary."
            )

        self.stdout.write(
            self.style.SUCCESS(
                "Cloudinary media migration verified: "
                f"files={len(files)}, uploaded={uploaded}, skipped={skipped}, "
                f"verified={verified}, failed={failed}, "
                f"product_images={len(field_names) - ProductImage.objects.count()}, "
                f"gallery_images={ProductImage.objects.count()}."
            )
        )
