from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from campaigns.models import IonosMailbox
from campaigns.ionos_sync import IonosAuthenticationError
from accounts.models import Tenant
from accounts.mailgun_secrets import decrypt_mailgun_secret


TEST_ENCRYPTION_KEY = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="


@override_settings(GMAIL_TOKEN_ENCRYPTION_KEY=TEST_ENCRYPTION_KEY)
class IonosMailboxApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username="ionosuser",
            email="ionosuser@example.com",
            password="test-password-value",
        )
        self.client.force_authenticate(user=self.user)

    @patch("accounts.views.validate_ionos_credentials", return_value=("123", 58))
    def test_connect_validates_and_encrypts_credentials(self, validate):
        response = self.client.post(
            reverse("accounts:ionos-mailbox"),
            {"email": "Mailbox@Example.com", "password": "mailbox-secret"},
            format="json",
        )

        mailbox = IonosMailbox.objects.get(tenant=self.user.tenant)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["connected"])
        self.assertEqual(response.data["email"], "mailbox@example.com")
        self.assertNotIn("password", response.data)
        self.assertNotIn("encrypted_password", response.data)
        self.assertNotEqual(mailbox.encrypted_password, "mailbox-secret")
        self.assertEqual(decrypt_mailgun_secret(mailbox.encrypted_password), "mailbox-secret")
        self.assertEqual(mailbox.last_uid, 57)
        validate.assert_called_once_with("mailbox@example.com", "mailbox-secret")

    @patch(
        "accounts.views.validate_ionos_credentials",
        side_effect=IonosAuthenticationError("IONOS rejected the mailbox credentials."),
    )
    def test_invalid_credentials_are_not_saved(self, _validate):
        response = self.client.post(
            reverse("accounts:ionos-mailbox"),
            {"email": "mailbox@example.com", "password": "wrong-secret"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(IonosMailbox.objects.exists())

    def test_status_and_disconnect_cannot_cross_tenant_boundary(self):
        other_user = get_user_model().objects.create_user(
            username="otherionosuser",
            email="otherionosuser@example.com",
            password="test-password-value",
        )
        IonosMailbox.objects.create(
            tenant=self.user.tenant,
            email="own@example.com",
            encrypted_password="own-encrypted",
            is_connected=True,
        )
        other_mailbox = IonosMailbox.objects.create(
            tenant=other_user.tenant,
            email="other@example.com",
            encrypted_password="other-encrypted",
            is_connected=True,
        )

        status_response = self.client.get(
            f"{reverse('accounts:ionos-mailbox')}?tenant_id={other_user.tenant_id}"
        )
        disconnect_response = self.client.delete(
            f"{reverse('accounts:ionos-mailbox')}?tenant_id={other_user.tenant_id}"
        )

        self.assertEqual(status_response.data["email"], "own@example.com")
        self.assertEqual(disconnect_response.status_code, 200)
        other_mailbox.refresh_from_db()
        self.assertEqual(other_mailbox.encrypted_password, "other-encrypted")
        self.assertTrue(other_mailbox.is_connected)

    def test_disconnection_clears_saved_credentials_and_cursor(self):
        mailbox = IonosMailbox.objects.create(
            tenant=self.user.tenant,
            email="own@example.com",
            encrypted_password="encrypted",
            is_connected=True,
            uid_validity="123",
            last_uid=57,
        )

        response = self.client.delete(reverse("accounts:ionos-mailbox"))

        self.assertEqual(response.status_code, 200)
        mailbox.refresh_from_db()
        self.assertFalse(mailbox.is_connected)
        self.assertEqual(mailbox.email, "")
        self.assertEqual(mailbox.encrypted_password, "")
        self.assertEqual(mailbox.last_uid, 0)

    @patch("accounts.views.validate_ionos_credentials", return_value=("123", 58))
    def test_superuser_can_connect_mailbox_for_selected_tenant(self, _validate):
        target_tenant = Tenant.objects.create(name="Selected tenant")
        admin = get_user_model().objects.create_user(
            username="ionosadmin",
            email="ionosadmin@example.com",
            password="test-password-value",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_authenticate(user=admin)

        response = self.client.post(
            f"{reverse('accounts:ionos-mailbox')}?tenant_id={target_tenant.pk}",
            {"email": "selected@example.com", "password": "mailbox-secret"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            IonosMailbox.objects.filter(
                tenant=target_tenant,
                email="selected@example.com",
                is_connected=True,
            ).exists()
        )
