#!/usr/bin/env bash
set -o errexit

# Migrations are idempotent.  Do not seed the catalogue here: a production
# deployment must never create products or modify imported catalogue data.
python manage.py migrate --noinput
exec gunicorn config.wsgi:application
