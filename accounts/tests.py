from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Module, Role


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


class UserNameMethodTests(APITestCase):
	def test_get_full_name_and_short_name_use_name_fields_with_username_fallback(self):
		user = get_user_model().objects.create_user(
			username="ada",
			email="ada@example.com",
			password="Violet-Engine-927!",
			first_name="Ada",
			last_name="Lovelace",
		)
		self.assertEqual(user.get_full_name(), "Ada Lovelace")
		self.assertEqual(user.get_short_name(), "Ada")

		user.first_name = ""
		user.last_name = ""
		self.assertEqual(user.get_full_name(), "ada")
		self.assertEqual(user.get_short_name(), "ada")


class RolePermissionCRUDTests(APITestCase):
	def setUp(self):
		user_model = get_user_model()
		self.staff_user = user_model(
			username="staff-admin",
			email="staff@example.com",
			is_staff=True,
		)
		self.staff_user.set_password("Tidal-Breeze-8247!")
		self.staff_user.save()
		self.client.force_authenticate(user=self.staff_user)
		self.role = Role.objects.create(name="Admin", code="admin")
		self.module = Module.objects.create(name="Campaigns", code="campaigns")

	def test_role_permission_crud_flow(self):
		create_response = self.client.post(reverse("accounts:role-permission-list"), {
			"role": self.role.id,
			"module": self.module.id,
			"can_view": True,
			"can_create": True,
			"can_edit": False,
			"can_delete": False,
		}, format="json")
		self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
		permission_id = create_response.data["id"]

		list_response = self.client.get(reverse("accounts:role-permission-list"))
		self.assertEqual(list_response.status_code, status.HTTP_200_OK)
		self.assertGreaterEqual(len(list_response.data), 1)

		detail_url = reverse("accounts:role-permission-detail", args=[permission_id])
		patch_response = self.client.patch(detail_url, {"can_edit": True, "can_delete": True}, format="json")
		self.assertEqual(patch_response.status_code, status.HTTP_200_OK)
		self.assertTrue(patch_response.data["can_edit"])
		self.assertTrue(patch_response.data["can_delete"])

		delete_response = self.client.delete(detail_url)
		self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)


class UserCRUDTests(APITestCase):
	def setUp(self):
		user_model = get_user_model()
		self.staff_user = user_model(
			username="staff-admin",
			email="staff@example.com",
			is_staff=True,
		)
		self.staff_user.set_password("Tidal-Breeze-8247!")
		self.staff_user.save()
		self.client.force_authenticate(user=self.staff_user)

	def test_staff_can_create_list_retrieve_update_and_delete_users(self):
		user_list_url = reverse("accounts:user-list")
		create_response = self.client.post(user_list_url, {
			"username": "managed-user",
			"email": "managed@example.com",
			"first_name": "Grace",
			"last_name": "Hopper",
			"password": "Saffron-Bridge-6284!",
		}, format="json")

		self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
		self.assertNotIn("password", create_response.data)
		user = get_user_model().objects.get(username="managed-user")
		self.assertTrue(user.check_password("Saffron-Bridge-6284!"))

		list_response = self.client.get(user_list_url)
		self.assertEqual(list_response.status_code, status.HTTP_200_OK)
		self.assertEqual(len(list_response.data), 2)

		user_detail_url = reverse("accounts:user-detail", args=[user.pk])
		retrieve_response = self.client.get(user_detail_url)
		self.assertEqual(retrieve_response.status_code, status.HTTP_200_OK)

		update_response = self.client.patch(user_detail_url, {
			"first_name": "Augusta",
			"password": "Copper-Cloud-3961!",
		}, format="json")
		self.assertEqual(update_response.status_code, status.HTTP_200_OK)
		user.refresh_from_db()
		self.assertEqual(user.first_name, "Augusta")
		self.assertTrue(user.check_password("Copper-Cloud-3961!"))

		delete_response = self.client.delete(user_detail_url)
		self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)
		self.assertFalse(get_user_model().objects.filter(pk=user.pk).exists())

	def test_non_staff_user_cannot_manage_users(self):
		regular_user = get_user_model()(
			username="regular-user",
			email="regular@example.com",
		)
		regular_user.set_password("Tidal-Breeze-8247!")
		regular_user.save()
		self.client.force_authenticate(user=regular_user)

		response = self.client.get(reverse("accounts:user-list"))

		self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
