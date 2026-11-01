import datetime

from django.conf import settings
from django.db import models
from django.db.models import Exists, OuterRef, Q, Subquery
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from fundus.catalog.isbn import normalize_isbn, validate_isbn
from fundus.core.models import SchoolScopedModel


class Category(SchoolScopedModel):
    name = models.CharField(_("Name"), max_length=100)
    default_loan_days = models.PositiveSmallIntegerField(
        _("Standard-Ausleihfrist (Tage)"),
        default=28,
        help_text=_("Wird beim Ausleihen als Rückgabedatum vorgeschlagen."),
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = _("Kategorie")
        verbose_name_plural = _("Kategorien")
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["school", "name"], name="category_unique_name"),
        ]

    def __str__(self):
        return self.name


class SupportFocus(SchoolScopedModel):
    """Förderschwerpunkt, z. B. Lernen, Sprache, emotionale und soziale Entwicklung."""

    name = models.CharField(_("Name"), max_length=100)

    history = HistoricalRecords()

    class Meta:
        verbose_name = _("Förderschwerpunkt")
        verbose_name_plural = _("Förderschwerpunkte")
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["school", "name"], name="supportfocus_unique_name"),
        ]

    def __str__(self):
        return self.name


class Location(SchoolScopedModel):
    room = models.CharField(_("Raum"), max_length=100)
    shelf = models.CharField(_("Regal/Fach"), max_length=100, blank=True)
    note = models.CharField(_("Hinweis"), max_length=200, blank=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name = _("Standort")
        verbose_name_plural = _("Standorte")
        ordering = ["room", "shelf"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "room", "shelf"], name="location_unique_room_shelf"
            ),
        ]

    def __str__(self):
        return f"{self.room} · {self.shelf}" if self.shelf else self.room


class Title(SchoolScopedModel):
    """Katalogeintrag: ein Werk oder Material, unabhängig von der Anzahl der Exemplare."""

    title = models.CharField(_("Titel"), max_length=300)
    subtitle = models.CharField(_("Untertitel"), max_length=300, blank=True)
    author = models.CharField(_("Autor/Herausgeber"), max_length=300, blank=True)
    publisher = models.CharField(_("Verlag"), max_length=200, blank=True)
    isbn = models.CharField(_("ISBN"), max_length=13, blank=True, validators=[validate_isbn])
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="titles", verbose_name=_("Kategorie")
    )
    support_focuses = models.ManyToManyField(
        SupportFocus, blank=True, related_name="titles", verbose_name=_("Förderschwerpunkte")
    )
    description = models.TextField(_("Beschreibung"), blank=True)
    cover = models.ImageField(_("Coverbild"), upload_to="covers/", blank=True)
    edition = models.CharField(_("Auflage"), max_length=100, blank=True)
    norm_year = models.PositiveSmallIntegerField(
        _("Normjahr"), null=True, blank=True, help_text=_("Bei Tests: Jahr der Normierung.")
    )
    contents = models.TextField(
        _("Inhaltsliste"),
        blank=True,
        help_text=_("Bei Testkoffern: ein Teil pro Zeile. Wird bei der Rückgabe abgefragt."),
    )
    lendable = models.BooleanField(
        _("ausleihbar"),
        default=False,
        help_text=_("Nur ausleihbare Titel werden per Scan ausgeliehen und zeigen ihren Status."),
    )
    approval_required = models.BooleanField(
        _("freigabepflichtig"),
        default=False,
        help_text=_("Ausleihe nur nach Freigabe und Übergabe durch die zuständige Person."),
    )
    responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="responsible_titles",
        verbose_name=_("zuständige Person"),
    )
    deputy = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deputy_titles",
        verbose_name=_("Vertretung"),
    )
    created_at = models.DateTimeField(_("angelegt am"), auto_now_add=True)
    updated_at = models.DateTimeField(_("geändert am"), auto_now=True)

    history = HistoricalRecords(m2m_fields=[support_focuses])

    class Meta:
        verbose_name = _("Titel")
        verbose_name_plural = _("Titel")
        ordering = ["title"]
        constraints = [
            models.CheckConstraint(
                condition=~Q(approval_required=True, lendable=False),
                name="title_approval_requires_lendable",
                violation_error_message=_("Freigabepflichtige Titel müssen ausleihbar sein."),
            ),
        ]

    def __str__(self):
        return self.title

    def clean_fields(self, exclude=None):
        self.isbn = normalize_isbn(self.isbn)
        super().clean_fields(exclude=exclude)

    def save(self, *args, **kwargs):
        self.isbn = normalize_isbn(self.isbn)
        super().save(*args, **kwargs)

    @property
    def contents_items(self):
        return [line.strip() for line in self.contents.splitlines() if line.strip()]

    def norm_is_outdated(self, max_age_years, today=None):
        if self.norm_year is None:
            return False
        today = today or timezone.localdate()
        return today.year - self.norm_year > max_age_years

    def default_due_date(self, start=None):
        start = start or timezone.localdate()
        return start + datetime.timedelta(days=self.category.default_loan_days)


class CopyQuerySet(models.QuerySet):
    def with_availability(self):
        """Ergänzt `is_lent`, `due_date` und `borrower_id` aus dem Ausleihprotokoll.

        Der Ausleihstatus wird nie am Exemplar gespeichert, sondern immer
        aus den Ausleihen abgeleitet.
        """
        from fundus.loans.models import Loan

        active = Loan.objects.filter(copy=OuterRef("pk"), status=Loan.Status.LENT)
        return self.annotate(
            is_lent=Exists(active),
            due_date=Subquery(active.values("due_date")[:1]),
            borrower_id=Subquery(active.values("borrower_id")[:1]),
        )


class Copy(SchoolScopedModel):
    """Exemplar: ein physisches Stück eines Titels mit eigener Inventarnummer."""

    class Condition(models.TextChoices):
        GOOD = "good", _("gut")
        WORN = "worn", _("Gebrauchsspuren")
        DAMAGED = "damaged", _("beschädigt")

    title = models.ForeignKey(
        Title, on_delete=models.PROTECT, related_name="copies", verbose_name=_("Titel")
    )
    inventory_number = models.CharField(
        _("Inventarnummer"),
        max_length=50,
        help_text=_("Eindeutig; steht im QR-Code des Etiketts."),
    )
    location = models.ForeignKey(
        Location,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="copies",
        verbose_name=_("Standort"),
    )
    condition = models.CharField(
        _("Zustand"), max_length=20, choices=Condition, default=Condition.GOOD
    )
    note = models.TextField(_("Notiz"), blank=True)
    incomplete = models.BooleanField(_("unvollständig"), default=False)
    created_at = models.DateTimeField(_("angelegt am"), auto_now_add=True)
    updated_at = models.DateTimeField(_("geändert am"), auto_now=True)

    objects = CopyQuerySet.as_manager()
    history = HistoricalRecords()

    class Meta:
        verbose_name = _("Exemplar")
        verbose_name_plural = _("Exemplare")
        ordering = ["inventory_number"]
        constraints = [
            models.UniqueConstraint(
                "school",
                Lower("inventory_number"),
                name="copy_unique_inventory_number",
                violation_error_message=_("Diese Inventarnummer ist schon vergeben."),
            ),
        ]

    def __str__(self):
        return f"{self.inventory_number} – {self.title}"

    def clean_fields(self, exclude=None):
        self.inventory_number = self.inventory_number.strip()
        super().clean_fields(exclude=exclude)

    def save(self, *args, **kwargs):
        self.inventory_number = self.inventory_number.strip()
        # Exemplare gehören immer zur Schule ihres Titels.
        self.school_id = self.title.school_id
        super().save(*args, **kwargs)

    @property
    def active_loan(self):
        from fundus.loans.models import Loan

        return self.loans.filter(status=Loan.Status.LENT).first()
