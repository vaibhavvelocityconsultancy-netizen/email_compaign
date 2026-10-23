import json

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.utils import timezone
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build, logger
from googleapiclient.errors import HttpError
from oauthlib.oauth2 import OAuth2Error
from requests import RequestException

from campaigns.models import GmailMailbox


GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.metadata"


class GmailOAuthError(Exception):
    pass


class GmailOAuthConfigurationError(GmailOAuthError):
    pass


def _validate_configuration():
    missing = [
        name
        for name, value in (
            ("GMAIL_OAUTH_CLIENT_ID", settings.GMAIL_OAUTH_CLIENT_ID),
            ("GMAIL_OAUTH_CLIENT_SECRET", settings.GMAIL_OAUTH_CLIENT_SECRET),
            ("GMAIL_OAUTH_REDIRECT_URI", settings.GMAIL_OAUTH_REDIRECT_URI),
            ("GMAIL_TOKEN_ENCRYPTION_KEY", settings.GMAIL_TOKEN_ENCRYPTION_KEY),
        )
        if not value
    ]
    if missing:
        raise GmailOAuthConfigurationError(
            "Gmail OAuth is not configured. Set: " + ", ".join(missing) + "."
        )


def _fernet():
    _validate_configuration()
    try:
        return Fernet(settings.GMAIL_TOKEN_ENCRYPTION_KEY.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as error:
        raise GmailOAuthConfigurationError(
            "GMAIL_TOKEN_ENCRYPTION_KEY must be a valid Fernet key."
        ) from error


def _flow(state=None, code_verifier=None):
    _validate_configuration()

    config = {
        "web": {
            "client_id": settings.GMAIL_OAUTH_CLIENT_ID,
            "client_secret": settings.GMAIL_OAUTH_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.GMAIL_OAUTH_REDIRECT_URI],
        }
    }

    flow = Flow.from_client_config(
        config,
        scopes=[GMAIL_SCOPE],
        state=state,
        redirect_uri=settings.GMAIL_OAUTH_REDIRECT_URI,
        code_verifier=code_verifier,
    )

    return flow


def create_gmail_authorization_url(state):
    _fernet()
    authorization_url, _ = _flow(state).authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return authorization_url


def complete_gmail_oauth(code):
    stage = "initialization"

    try:
        fernet = _fernet()

        stage = "create OAuth flow"
        flow = _flow()

        stage = "exchange authorization code"
        flow.fetch_token(code=code)
        credentials = flow.credentials

        if not credentials.refresh_token:
            raise GmailOAuthError(
                "Google did not provide a refresh token. "
                "Revoke the existing grant and authorize again."
            )

        stage = "fetch Gmail profile"
        service = build(
            "gmail",
            "v1",
            credentials=credentials,
            cache_discovery=False,
        )
        profile = service.users().getProfile(userId="me").execute()

        mailbox_email = profile.get("emailAddress", "").strip().lower()
        history_id = str(profile.get("historyId", ""))

        if not mailbox_email or not history_id:
            raise GmailOAuthError(
                "Google returned incomplete Gmail profile metadata."
            )

        stage = "encrypt credentials"
        encrypted_credentials = fernet.encrypt(
            credentials.to_json().encode("utf-8")
        ).decode("ascii")

        stage = "save mailbox"
        mailbox, _ = GmailMailbox.objects.get_or_create(pk=1)
        mailbox.email = mailbox_email
        mailbox.encrypted_credentials = encrypted_credentials
        mailbox.history_id = history_id
        mailbox.last_sync_at = timezone.now()
        mailbox.save(
            update_fields=[
                "email",
                "encrypted_credentials",
                "history_id",
                "last_sync_at",
                "updated_at",
            ]
        )

        return mailbox

    except GmailOAuthError:
        raise
    except (
        GoogleAuthError,
        HttpError,
        OAuth2Error,
        RequestException,
        ValueError,
    ) as error:
        logger.exception(
            "Google OAuth token exchange failed: %s",
            type(error).__name__,
        )
        raise GmailOAuthError(
            f"Google authorization failed during: {stage}."
        ) from error
        
        
def get_gmail_service(mailbox):
    fernet = _fernet()
    if not mailbox.encrypted_credentials:
        raise GmailOAuthError("Gmail is not connected. Authorize a mailbox first.")
    try:
        credentials_json = fernet.decrypt(
            mailbox.encrypted_credentials.encode("ascii")
        ).decode("utf-8")
        credentials = Credentials.from_authorized_user_info(
            json.loads(credentials_json),
            scopes=[GMAIL_SCOPE],
        )
    except (
        InvalidToken,
        KeyError,
        TypeError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
    ) as error:
        raise GmailOAuthConfigurationError(
            "Stored Gmail credentials cannot be decrypted. Check the token encryption key."
        ) from error

    if credentials.expired and credentials.refresh_token:
        try:
            credentials.refresh(Request())
        except GoogleAuthError as error:
            if "invalid_grant" in str(error).lower():
                mailbox.encrypted_credentials = ""
                mailbox.history_id = ""
                mailbox.save(
                    update_fields=[
                        "encrypted_credentials",
                        "history_id",
                        "updated_at",
                    ]
                )
                raise GmailOAuthError(
                    "Gmail authorization was revoked or expired. Authorize the mailbox again."
                ) from error
            raise GmailOAuthError("Gmail token refresh failed; retry the sync later.") from error
        mailbox.encrypted_credentials = fernet.encrypt(
            credentials.to_json().encode("utf-8")
        ).decode("ascii")
        mailbox.save(update_fields=["encrypted_credentials", "updated_at"])
    elif not credentials.valid:
        raise GmailOAuthError(
            "Gmail credentials are expired or invalid. Authorize the mailbox again."
        )

    try:
        return build("gmail", "v1", credentials=credentials, cache_discovery=False)
    except (GoogleAuthError, HttpError) as error:
        raise GmailOAuthError("Gmail API client initialization failed.") from error
