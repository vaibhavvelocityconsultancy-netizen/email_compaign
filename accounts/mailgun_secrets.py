import os

from cryptography.fernet import Fernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def get_encryption_key():
    key = getattr(settings, "GMAIL_TOKEN_ENCRYPTION_KEY", "") or os.environ.get(
        "GMAIL_TOKEN_ENCRYPTION_KEY", ""
    )
    return key.strip()


def _fernet():
    key = get_encryption_key()
    if not key:
        raise ImproperlyConfigured(
            "GMAIL_TOKEN_ENCRYPTION_KEY must be configured to encrypt stored credentials."
        )
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as error:
        raise ImproperlyConfigured(
            "GMAIL_TOKEN_ENCRYPTION_KEY must be a valid Fernet key."
        ) from error


def encrypt_mailgun_secret(value):
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_mailgun_secret(value):
    return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
