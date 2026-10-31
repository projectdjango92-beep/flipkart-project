#!/usr/bin/env bash
set -o errexit

# A Render persistent disk is mounted only at runtime, not while building.
# These are safe on every restart: migrations are non-destructive and the
# catalogue command only creates records that are missing.
python manage.py migrate --noinput
python manage.py seed_catalogue
exec gunicorn config.wsgi:application
