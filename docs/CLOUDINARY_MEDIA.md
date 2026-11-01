# Cloudinary product media

The product and gallery fields retain their existing relative names, such as
`products/demo_1.webp` and `products/gallery/images.jpeg`. No database data
needs to be edited for the storage change.

## Configure secrets

Set these private environment variables locally and in Render. Do not put their
values in source control or this document:

- `CLOUDINARY_CLOUD_NAME`
- `CLOUDINARY_API_KEY`
- `CLOUDINARY_API_SECRET`

All three are required. The application deliberately stops at startup if only
some are set. With none set, local development keeps using `media/`.

## Copy and verify the existing media

From the project directory, after the variables are set:

```powershell
python manage.py migrate_media_to_cloudinary
```

The command copies missing assets only. It preserves each folder/filename,
verifies the remote byte size for every local file, verifies the 100 product
images and 9 gallery records, does not modify database rows, and never removes
the local source files. It can safely be re-run after an interrupted upload.

For a no-network preflight:

```powershell
python manage.py migrate_media_to_cloudinary --dry-run
```

Deploy only after the command reports a fully verified migration. Cloudinary
storage will then generate HTTPS asset URLs for existing `ImageField` values and
for future uploads from Django admin.
