"""Cloudinary storage compatibility for existing ImageField filenames."""

from pathlib import PurePosixPath

import cloudinary
from cloudinary_storage.storage import MediaCloudinaryStorage


class ExistingFilenameCloudinaryStorage(MediaCloudinaryStorage):
    """Resolve legacy ``products/name.ext`` values as Cloudinary IDs plus format.

    Cloudinary's Django storage normally stores extension-free public IDs. The
    imported catalogue instead retains filesystem-style names in its ImageField
    values. Uploads retain the same Cloudinary public IDs, while this adapter
    converts legacy names to the matching public ID and output format at URL
    generation time. New admin uploads continue to use the parent storage.
    """

    def _get_url(self, name):
        name = self._prepend_prefix(name)
        path = PurePosixPath(name)
        suffix = path.suffix
        if not suffix:
            return super()._get_url(name)

        resource = cloudinary.CloudinaryResource(
            str(path.with_suffix("")),
            format=suffix.lstrip("."),
            default_resource_type=self._get_resource_type(name),
        )
        return resource.url
