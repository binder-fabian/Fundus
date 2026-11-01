from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("E-Mail-Adresse fehlt")
        user = self.model(email=self.normalize_email(email), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self._create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """Benutzerkonto einer Lehrkraft oder Verwaltungsperson; Anmeldung per E-Mail."""

    email = models.EmailField(_("E-Mail-Adresse"), unique=True)
    first_name = models.CharField(_("Vorname"), max_length=150, blank=True)
    last_name = models.CharField(_("Nachname"), max_length=150, blank=True)
    is_active = models.BooleanField(_("aktiv"), default=True)
    is_staff = models.BooleanField(_("Zugang zur Admin-Oberfläche"), default=False)
    date_joined = models.DateTimeField(_("angelegt am"), default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"

    class Meta:
        verbose_name = _("Benutzer")
        verbose_name_plural = _("Benutzer")
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return self.get_full_name() or self.email

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def get_short_name(self):
        return self.first_name or self.email
