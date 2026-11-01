from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("E-Mail-Adresse fehlt")
        user = self.model(email=self.normalize_email(email).lower(), **extra_fields)
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
        extra_fields.setdefault("role", Role.ADMIN)
        return self._create_user(email, password, **extra_fields)

    def get_by_natural_key(self, username):
        # Anmeldung unabhängig von Groß-/Kleinschreibung der E-Mail-Adresse.
        return self.get(email__iexact=username)

    def active_admins(self):
        return self.filter(is_active=True, role=Role.ADMIN)


class Role(models.TextChoices):
    """Globale Rolle. „Zuständige Person“ ist keine Rolle, sondern ergibt sich
    aus der Zuordnung am Titel."""

    ADMIN = "admin", _("Administrator")
    MANAGER = "manager", _("Verwalter")
    TEACHER = "teacher", _("Lehrkraft")
    SECRETARY = "secretary", _("Sekretariat")


class User(AbstractBaseUser, PermissionsMixin):
    """Benutzerkonto einer Lehrkraft oder Verwaltungsperson; Anmeldung per E-Mail."""

    email = models.EmailField(_("E-Mail-Adresse"), unique=True)
    role = models.CharField(_("Rolle"), max_length=20, choices=Role, default=Role.TEACHER)
    first_name = models.CharField(_("Vorname"), max_length=150, blank=True)
    last_name = models.CharField(_("Nachname"), max_length=150, blank=True)
    is_active = models.BooleanField(_("aktiv"), default=True)
    is_staff = models.BooleanField(_("Zugang zur Admin-Oberfläche"), default=False)
    date_joined = models.DateTimeField(_("angelegt am"), default=timezone.now)

    objects = UserManager()
    history = HistoricalRecords(excluded_fields=["password", "last_login"])

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

    # Rechte nach Rolle. Administratoren dürfen alles, was Verwalter dürfen.
    @property
    def is_admin(self):
        return self.is_active and self.role == Role.ADMIN

    @property
    def can_manage_catalog(self):
        return self.is_active and self.role in (Role.ADMIN, Role.MANAGER)

    @property
    def can_manage_users(self):
        return self.is_admin

    @property
    def invitation_pending(self):
        """Eingeladen, aber noch kein Passwort gesetzt."""
        return not self.has_usable_password() and self.last_login is None


class FailedLogin(models.Model):
    """Fehlgeschlagener Anmeldeversuch, für die Sperre nach zu vielen Versuchen.
    Einträge werden nach einem Tag gelöscht."""

    username = models.CharField(max_length=254, db_index=True)
    ip = models.GenericIPAddressField(null=True, db_index=True)
    at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = _("fehlgeschlagene Anmeldung")
        verbose_name_plural = _("fehlgeschlagene Anmeldungen")

    def __str__(self):
        return f"{self.username} ({self.at:%d.%m.%Y %H:%M})"
