from types import SimpleNamespace
from datetime import timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from campaigns.models import GmailMailbox
from .gmail_oauth import GMAIL_SCOPE, create_gmail_authorization_url


@override_settings(
    GMAIL_OAUTH_CLIENT_ID="test-client-id",
    GMAIL_OAUTH_CLIENT_SECRET="test-client-secret",
    GMAIL_OAUTH_REDIRECT_URI="http://127.0.0.1:8000/api/auth/google/callback/",
    GMAIL_TOKEN_ENCRYPTION_KEY="MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
)
class GoogleOAuthViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username="gmailoauthuser",
            email="gmailoauthuser@example.com",
            password="test-password-value",
            is_staff=True,
        )

    def test_authorization_requires_authentication_and_allows_tenant_users(self):
        response = self.client.get(reverse("accounts:google-authorize"))

        self.assertEqual(response.status_code, 401)

        regular_user = get_user_model().objects.create_user(
            username="regulargmailuser",
            email="regulargmailuser@example.com",
            password="test-password-value",
        )
        self.client.force_authenticate(user=regular_user)
        tenant_response = self.client.get(reverse("accounts:google-authorize"))
        self.assertEqual(tenant_response.status_code, 200)
    def test_authorization_url_requests_metadata_scope_only(self):
        authorization_url, encrypted_code_verifier = create_gmail_authorization_url(
            "oauth-state-value"
        )
        query = parse_qs(urlparse(authorization_url).query)

        self.assertEqual(query["scope"], [GMAIL_SCOPE])
        self.assertEqual(query["state"], ["oauth-state-value"])
        self.assertEqual(query["access_type"], ["offline"])
        self.assertEqual(query["prompt"], ["select_account consent"])
        self.assertTrue(query["code_challenge"])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertTrue(encrypted_code_verifier)

    @patch("accounts.views.create_gmail_authorization_url")
    def test_authorization_persists_only_a_hash_of_one_time_state(self, create_url):
        create_url.side_effect = lambda state: (
            f"https://accounts.google.test/?state={state}",
            "encrypted-code-verifier",
        )
        self.client.force_authenticate(user=self.user)

        response = self.client.get(reverse("accounts:google-authorize"))

        self.assertEqual(response.status_code, 200)
        state = create_url.call_args.args[0]
        self.assertEqual(response.data["authorization_url"], f"https://accounts.google.test/?state={state}")
        mailbox = GmailMailbox.objects.get(pk=1)
        self.assertNotEqual(mailbox.oauth_state_hash, state)
        self.assertEqual(len(mailbox.oauth_state_hash), 64)
        self.assertEqual(mailbox.oauth_code_verifier, "encrypted-code-verifier")

    @patch("accounts.views.decrypt_gmail_oauth_code_verifier", return_value="test-verifier")
    @patch("accounts.views.complete_gmail_oauth")
    @patch("accounts.views.create_gmail_authorization_url")
    def test_callback_validates_and_consumes_state(
        self,
        create_url,
        complete_oauth,
        decrypt_verifier,
    ):
        create_url.side_effect = lambda state: (
            f"https://accounts.google.test/?state={state}",
            "encrypted-code-verifier",
        )
        self.client.force_authenticate(user=self.user)
        self.client.get(reverse("accounts:google-authorize"))
        state = create_url.call_args.args[0]
        complete_oauth.return_value = SimpleNamespace(email="replies@example.com")
        callback_url = reverse("accounts:google-callback")

        invalid_response = self.client.get(
            callback_url,
            {"state": "incorrect-state", "code": "test-code"},
        )
        response = self.client.get(
            callback_url,
            {"state": state, "code": "test-code"},
        )
        replay_response = self.client.get(
            callback_url,
            {"state": state, "code": "test-code"},
        )

        self.assertEqual(invalid_response.status_code, 400)
        self.assertEqual(response.status_code, 302)
        self.assertIn("gmail=connected", response["Location"])
        self.assertEqual(replay_response.status_code, 400)
        decrypt_verifier.assert_called_once_with("encrypted-code-verifier")
        mailbox = GmailMailbox.objects.get(pk=1)
        complete_oauth.assert_called_once_with(
            "test-code",
            code_verifier="test-verifier",
            mailbox=mailbox,
        )
        self.assertEqual(mailbox.oauth_code_verifier, "")

    def test_connection_status_and_disconnect_are_limited_to_current_tenant(self):
        from accounts.views import GmailConnectionView

        own = GmailMailbox.objects.create(
            tenant=self.user.tenant,
            email="own@example.com",
            encrypted_credentials="encrypted-own",
            history_id="100",
        )
        other_user = get_user_model().objects.create_user(
            username="othergmailtenant",
            email="othergmailtenant@example.com",
            password="test-password-value",
        )
        other = GmailMailbox.objects.create(
            tenant=other_user.tenant,
            email="other@example.com",
            encrypted_credentials="encrypted-other",
            history_id="200",
        )
        self.client.force_authenticate(user=self.user)

        status_response = self.client.get(
            reverse("accounts:gmail-connection"),
            {"tenant_id": other.tenant_id},
        )
        disconnect_response = self.client.delete(reverse("accounts:gmail-connection"))

        self.assertEqual(status_response.data["email"], own.email)
        self.assertTrue(status_response.data["connected"])
        self.assertEqual(disconnect_response.status_code, 200)
        own.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(own.encrypted_credentials, "")
        self.assertEqual(other.encrypted_credentials, "encrypted-other")

    @patch("accounts.views.create_gmail_authorization_url")
    def test_expired_state_is_rejected(self, create_url):
        create_url.side_effect = lambda state: (
            f"https://accounts.google.test/?state={state}",
            "encrypted-code-verifier",
        )
        self.client.force_authenticate(user=self.user)
        self.client.get(reverse("accounts:google-authorize"))
        state = create_url.call_args.args[0]
        mailbox = GmailMailbox.objects.get(pk=1)
        mailbox.oauth_state_created_at = timezone.now() - timedelta(minutes=11)
        mailbox.save(update_fields=["oauth_state_created_at"])

        response = self.client.get(
            reverse("accounts:google-callback"),
            {"state": state, "code": "test-code"},
        )

        self.assertEqual(response.status_code, 400)
