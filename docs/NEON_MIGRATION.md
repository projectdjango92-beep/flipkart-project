# Neon PostgreSQL migration and Render deployment

This project uses SQLite whenever `DATABASE_URL` is unset. When it is set,
`dj-database-url` configures Django for PostgreSQL, forces SSL unless a stricter
`sslmode` was supplied, uses a ten-second connection timeout, and enables
connection health checks. It supports Neon pooled URLs without embedding a
credential in source control.

## One-time SQLite to Neon transfer

Do this during a maintenance window: stop writes to the deployed SQLite site,
then make the backup and fixture from the same final SQLite file. Do **not** run
`seed_catalogue` after the import. It is a development/bootstrap command only.

These commands are for Windows PowerShell, from the project directory. They do
not print secrets; set `DATABASE_URL` from the Neon dashboard or Render's
environment page, not in a command history or a committed file.

```powershell
New-Item -ItemType Directory -Force .\private-backups | Out-Null
Copy-Item .\db.sqlite3 .\private-backups\db.sqlite3.before-neon-migration
python manage.py check
python manage.py dumpdata --exclude contenttypes --exclude auth.Permission --indent 2 --output .\private-backups\sqlite-export.json
```

Keep `private-backups` outside Git (it contains users and hashed passwords).
The fixture retains primary keys and foreign keys, including users, customer
profiles, products, gallery images, orders, order items, and migration-era app
records. Django preserves password hashes; no passwords are converted or
revealed.

In Render, add a secret environment variable named `DATABASE_URL` with the
**pooled** connection string copied from Neon. Also set
`DJANGO_SECRET_KEY`, `DJANGO_DEBUG=False`,
`DJANGO_ALLOWED_HOSTS=flipkart-project-yxhg.onrender.com`, and
`DJANGO_CSRF_TRUSTED_ORIGINS=https://flipkart-project-yxhg.onrender.com`.
Do not set `DJANGO_DB_PATH` for this deployment.

Before loading data, use a local shell or Render Shell with `DATABASE_URL`
configured. The target must be a new/empty Neon database. These commands only
migrate schema and inspect data before the load:

```powershell
python manage.py migrate --noinput
python manage.py verify_database --require-postgresql --require-empty-business-data
python manage.py loaddata .\private-backups\sqlite-export.json
python manage.py verify_database --require-postgresql
```

If the empty-target check fails, stop. Do not use `flush`, `reset_db`, SQL
`DROP`, or `--fake` to force the import. Restore from the SQLite backup or use
a newly created Neon branch/database instead. After a successful load, compare
the non-sensitive record totals with the original SQLite database and test an
existing admin login. Django's fixture loader resets PostgreSQL sequences, so
new records receive IDs beyond imported primary keys.

## Render deployment

Push these changes through the existing `main` branch workflow. Render's build
script installs dependencies and runs `collectstatic`; its start script runs
idempotent Django migrations and starts Gunicorn. It intentionally does not
seed catalogue data or create SQLite data. Confirm the build log shows
`psycopg` installed and the release starts only after `migrate` succeeds.

## Media persistence

WhiteNoise serves static files, not user/product media. In this repository the
existing `media/` files work locally and only when they are present in the
deployed filesystem, but Render's normal filesystem is ephemeral. For durable
uploads use object storage before relying on new production uploads: Cloudinary
has a limited free tier; Amazon S3, Cloudflare R2, and Backblaze B2 are paid
usage-based options (some offer free allowances). Configure a storage backend
and copy existing media only after choosing a provider; this change deliberately
does not rename or move any existing image files.

## Live verification checklist

- Confirm `python manage.py verify_database --require-postgresql` succeeds in
  the Render environment.
- Check products, gallery images, existing orders, and product image URLs.
- Log in with an existing account and the admin account; verify logout and a
  normal session refresh.
- Register a test account, verify duplicate usernames are rejected, then remove
  that test account only through the admin if desired.
- Place a test order and verify it appears in order history and admin.
- Confirm HTTPS redirects, CSRF-protected POSTs, and static CSS/JavaScript load.
