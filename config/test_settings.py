"""Safe, local-only settings for Django's automated test suite."""

from .settings import *  # noqa: F403

# Tests must never create, truncate, or drop a database on Neon, even when a
# developer's local .env contains DATABASE_URL.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "test.sqlite3",  # noqa: F405
    }
}
