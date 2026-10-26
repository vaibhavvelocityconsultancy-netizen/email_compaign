from cryptography.fernet import Fernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def _fernet():
    key = settings.GMAIL_TOKEN_ENCRYPTION_KEY
    if not key:
        raise ImproperlyConfigured(
            "GMAIL_TOKEN_ENCRYPTION_KEY must be configured to store Mailgun secrets."
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
