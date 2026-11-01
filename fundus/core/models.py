from django.db import models
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords


class School(models.Model):
    """Eine Schule. Im MVP gibt es genau eine; das Modell bereitet die
    Mandantenfähigkeit (mehrere Schulen pro Instanz) vor."""

    name = models.CharField(_("Name"), max_length=200)
    created_at = models.DateTimeField(_("angelegt am"), auto_now_add=True)

    class Meta:
        verbose_name = _("Schule")
        verbose_name_plural = _("Schulen")
        ordering = ["pk"]

    def __str__(self):
        return self.name


def default_school_id():
    """Standardwert für Fremdschlüssel auf die Schule: die erste (und im MVP einzige)."""
    school = School.objects.order_by("pk").first()
    if school is None:
        school = School.objects.create(name="Meine Schule")
    return school.pk


class SchoolScopedModel(models.Model):
    school = models.ForeignKey(
        School,
        on_delete=models.PROTECT,
        default=default_school_id,
        related_name="+",
        verbose_name=_("Schule"),
    )

    class Meta:
        abstract = True


class SchoolSettings(models.Model):
    """Einstellungen, die Administratoren in der Oberfläche ändern können."""

    school = models.OneToOneField(
        School, on_delete=models.CASCADE, related_name="settings", verbose_name=_("Schule")
    )
    number_prefix = models.CharField(
        _("Präfix für Inventarnummern"),
        max_length=20,
        blank=True,
        default="FS-",
        help_text=_("Steht vor der laufenden Nummer, z. B. „FS-“. Darf leer sein."),
    )
    number_digits = models.PositiveSmallIntegerField(
        _("Stellen der laufenden Nummer"),
        default=4,
        help_text=_("Mit führenden Nullen aufgefüllt: 4 Stellen ergibt 0101."),
    )
    next_number = models.PositiveIntegerField(
        _("nächste laufende Nummer"),
        default=1,
        help_text=_("Höhere vorhandene Nummern mit diesem Präfix werden automatisch übersprungen."),
    )
    outdated_norm_years = models.PositiveSmallIntegerField(
        _("Tests gelten als veraltet nach (Jahren)"),
        default=10,
        help_text=_("Gemessen am Normjahr. Solche Tests bekommen einen Hinweis."),
    )
    isbn_lookup_enabled = models.BooleanField(
        _("ISBN-Abruf aus dem Internet"),
        default=True,
        help_text=_(
            "Fragt Buchdaten bei der Deutschen Nationalbibliothek und Open Library ab. "
            "Dabei wird nur die ISBN übermittelt."
        ),
    )
    label_offset_x = models.DecimalField(
        _("Druckversatz waagerecht (mm)"),
        max_digits=4,
        decimal_places=1,
        default=0,
        help_text=_("Positiv schiebt nach rechts. Mit der Testseite ermitteln."),
    )
    label_offset_y = models.DecimalField(
        _("Druckversatz senkrecht (mm)"),
        max_digits=4,
        decimal_places=1,
        default=0,
        help_text=_("Positiv schiebt nach unten."),
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = _("Einstellungen")
        verbose_name_plural = _("Einstellungen")

    def __str__(self):
        return str(_("Einstellungen"))

    @classmethod
    def current(cls):
        settings, _created = cls.objects.get_or_create(school_id=default_school_id())
        return settings

    def format_number(self, number):
        return f"{self.number_prefix}{number:0{self.number_digits}d}"
