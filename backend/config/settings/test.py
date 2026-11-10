from cryptography.fernet import Fernet

from .base import *  # noqa: F403

DEBUG = False
ADMIN_TOKEN = "a" * 32
ENCRYPTION_KEY = Fernet.generate_key().decode()
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
