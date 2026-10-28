from django.db import models
from django.contrib.auth.models import (
    AbstractBaseUser,
    PermissionsMixin,
    BaseUserManager,
)


class Tenant(models.Model):
    name = models.CharField(max_length=300)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class TenantMailgunSettings(models.Model):
    tenant = models.OneToOneField(
        Tenant,
        on_delete=models.CASCADE,
        related_name="mailgun_settings",
    )
    default_from_email = models.CharField(max_length=320)
    reply_to_email = models.CharField(max_length=320, blank=True, default="")
    sender_domain = models.CharField(max_length=255)
    encrypted_api_key = models.TextField(blank=True)
    encrypted_webhook_signing_key = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Mailgun settings for {self.tenant}"


class UserManager(BaseUserManager):
    def create_user(self, username, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required")

        email = self.normalize_email(email)

        if extra_fields.get("tenant") is None:
            full_name = " ".join(
                part.strip()
                for part in (
                    extra_fields.get("first_name", ""),
                    extra_fields.get("last_name", ""),
                )
                if part and part.strip()
            )
            extra_fields["tenant"] = Tenant.objects.create(name=full_name or email)

        user = self.model(
            username=username,
            email=email,
            **extra_fields,
        )

        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if not extra_fields["is_staff"]:
            raise ValueError("Superuser must have is_staff=True")

        if not extra_fields["is_superuser"]:
            raise ValueError("Superuser must have is_superuser=True")

        return self.create_user(
            username=username,
            email=email,
            password=password,
            **extra_fields,
        )

class Role(models.Model):
    name = models.CharField(max_length=50, unique=True)
    code = models.SlugField(max_length=50, unique=True)

    def __str__(self):
        return self.name


class Module(models.Model):
    name = models.CharField(max_length=80)
    code = models.SlugField(max_length=80, unique=True)

    def __str__(self):
        return self.name


class RolePermission(models.Model):
    role = models.ForeignKey(
        Role,
        on_delete=models.CASCADE,
        related_name="permissions"
    )

    module = models.ForeignKey(
        Module,
        on_delete=models.CASCADE,
        related_name="permissions"
    )

    can_view = models.BooleanField(default=False)
    can_create = models.BooleanField(default=False)
    can_edit = models.BooleanField(default=False)
    can_delete = models.BooleanField(default=False)

    class Meta:
        unique_together = ("role", "module")

    def __str__(self):
        return f"{self.role.name} - {self.module.name}"


class User(AbstractBaseUser, PermissionsMixin):

    username = models.CharField(
        max_length=150,
        unique=True
    )

    email = models.EmailField(
        unique=True
    )

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        related_name="users",
        null=True,
        blank=True,
    )

    first_name = models.CharField(
        max_length=30,
        blank=True
    )

    last_name = models.CharField(
        max_length=30,
        blank=True
    )

    role = models.ForeignKey(
        Role,
        on_delete=models.PROTECT,
        null=True,
        blank=True
    )

    is_active = models.BooleanField(default=True)

    is_staff = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = "username"

    REQUIRED_FIELDS = ["email"]

    def save(self, *args, **kwargs):
        if self.tenant_id is None:
            self.tenant = Tenant.objects.create(name=self.get_full_name())
        super().save(*args, **kwargs)

    def __str__(self):
        return self.username

    def get_full_name(self):
        full_name = " ".join(
            part.strip() for part in (self.first_name, self.last_name) if part and part.strip()
        )
        return full_name or self.username

    def get_short_name(self):
        return self.first_name or self.username