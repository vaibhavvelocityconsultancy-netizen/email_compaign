from django.test import TestCase

from .models import Role, Tenant
from .serializers import RegisterSerializer


class TenantRegistrationTests(TestCase):
    def test_registration_creates_a_named_private_tenant(self):
        existing_tenant_count = Tenant.objects.count()
        users = []
        for email, first_name, last_name in (
            ("first@example.com", "First", "Account"),
            ("second@example.com", "Second", "Account"),
        ):
            serializer = RegisterSerializer(
                data={
                    "first_name": first_name,
                    "last_name": last_name,
                    "email": email,
                    "password": "ValidPassword!9384",
                }
            )
            self.assertTrue(serializer.is_valid(), serializer.errors)
            users.append(serializer.save())

        self.assertNotEqual(users[0].tenant_id, users[1].tenant_id)
        self.assertEqual(users[0].tenant.name, "First Account")
        self.assertEqual(users[1].tenant.name, "Second Account")
        admin_role = Role.objects.get(code="admin")
        self.assertEqual(admin_role.name, "Admin")
        self.assertEqual(users[0].role, admin_role)
        self.assertEqual(users[1].role, admin_role)
        self.assertFalse(users[0].is_staff)
        self.assertFalse(users[0].is_superuser)
        self.assertEqual(Tenant.objects.count(), existing_tenant_count + 2)
