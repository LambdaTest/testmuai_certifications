"""
Cross-cutting models — currently just the user.

``home`` holds what isn't part of the assessment domain: accounts, the candidate
dashboard, account settings. Everything about certifications, booking, sitting an
exam, grading, and credentials lives in ``apps.exam``.

Dependencies point one way: ``home`` may import from ``exam``; ``exam`` reaches
the user only through ``settings.AUTH_USER_MODEL``.
"""

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    """Keyed on external_id rather than a username."""

    use_in_migrations = True

    def create_user(self, external_id, email=None, **extra):
        if not external_id:
            raise ValueError("external_id is required")
        user = self.model(
            external_id=external_id,
            email=self.normalize_email(email) if email else "",
            **extra,
        )
        # Identity lives with the OIDC provider; nobody logs in here.
        user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, external_id, email=None, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("role", User.Role.ADMIN)
        user = self.model(
            external_id=external_id,
            email=self.normalize_email(email) if email else "",
            **extra,
        )
        # The only accounts with a real password are local superusers, so the
        # Django admin stays reachable before OIDC is wired up.
        user.set_password(password)
        user.save(using=self._db)
        return user


class User(AbstractUser):
    """
    This app never authenticates anyone directly. Identity comes from TestMu AI's
    existing login over OIDC — see docs/auth.md. No sign-in form, no
    usable password.

    AUTH_USER_MODEL is baked into Django's migration graph, so this had to be
    right before the first migration.
    """

    class Role(models.TextChoices):
        CANDIDATE = "candidate", "Candidate"
        EXAMINER = "examiner", "Examiner"
        ADMIN = "admin", "Admin"

    # Replaced by external_id / display_name.
    username = None
    first_name = None
    last_name = None

    #: The OIDC ``sub`` from TestMu AI's identity provider. Opaque — never
    #: parsed, never assumed numeric, never assumed to be an email.
    external_id = models.CharField(max_length=255, unique=True)

    #: Refreshed from the provider on every login. A contact attribute, never an
    #: identity — people change email addresses.
    email = models.EmailField(blank=True)

    #: Single field on purpose. Name structures vary too much across cultures for
    #: first/last to be safe, and this string ends up on a credential.
    display_name = models.CharField(max_length=255, blank=True)

    contact_number = models.CharField(max_length=32, blank=True)

    #: Held locally. The identity provider establishes who you are; it must not
    #: be able to grant permissions here.
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.CANDIDATE)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "external_id"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        db_table = "users"

    def __str__(self):
        return self.display_name or self.email or self.external_id