from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase


class RegistrationTests(APITestCase):
	def test_register_creates_user_and_returns_tokens(self):
		response = self.client.post(reverse("accounts:register"), {
			"first_name": "Ada",
			"last_name": "Lovelace",
			"email": "ada@example.com",
			"password": "Violet-Engine-927!",
		}, format="json")

		self.assertEqual(response.status_code, status.HTTP_201_CREATED)
		self.assertIn("access", response.data)
		self.assertIn("refresh", response.data)
		self.assertEqual(response.data["user"]["email"], "ada@example.com")
		user = get_user_model().objects.get(email="ada@example.com")
		self.assertTrue(user.check_password("Violet-Engine-927!"))
