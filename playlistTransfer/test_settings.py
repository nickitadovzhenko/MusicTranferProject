"""
Test settings for MusicTransferProject.

Use this settings file when running tests to avoid needing a live MySQL server
and to run Celery tasks synchronously.

    python manage.py test --settings=playlistTransfer.test_settings
"""
import os

# Ensure minimum required env vars exist before importing base settings
os.environ.setdefault('SECRET_KEY', 'django-insecure-test-key-for-testing-only-do-not-use-in-production')
os.environ.setdefault('SPOTIFY_CLIENT_ID', 'test_spotify_client_id')
os.environ.setdefault('SPOTIFY_CLIENT_SECRET', 'test_spotify_client_secret')
os.environ.setdefault('SPOTIFY_REDIRECT_URI', 'http://localhost/spotify/callback')
os.environ.setdefault('GOOGLE_CLIENT_ID', 'test_google_client_id')
os.environ.setdefault('GOOGLE_CLIENT_SECRET', 'test_google_client_secret')
os.environ.setdefault('GOOGLE_REDIRECT_URI', 'http://localhost/youtube/callback')

from .settings import *  # noqa: E402, F401, F403

# --- Database ---
# Use in-memory SQLite so no MySQL server is needed when running tests
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

# --- Celery ---
# Run tasks synchronously and re-raise exceptions so test assertions work
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# --- Email ---
# Capture emails in memory instead of sending them
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
