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
    reminders_enabled = models.BooleanField(
        _("E-Mail-Erinnerungen verschicken"),
        default=True,
    )
    reminder_days_before = models.PositiveSmallIntegerField(
        _("Erinnerung … Tage vor Ablauf"), default=1
    )
    overdue_notice_days = models.PositiveSmallIntegerField(
        _("Überfällig-Hinweis … Tage nach Ablauf"), default=3
    )
    escalate_days = models.PositiveSmallIntegerField(
        _("Zusätzlich an die Verwaltung … Tage nach Ablauf"), default=14
    )
    request_reminder_days = models.PositiveSmallIntegerField(
        _("Team erinnern, wenn eine Anfrage … Tage unbearbeitet ist"), default=3
    )
    request_pickup_days = models.PositiveSmallIntegerField(
        _("Genehmigte Anfragen verfallen nach … Tagen ohne Abholung"), default=14
    )
    reorder_email = models.EmailField(
        _("Nachbestellhinweise zusätzlich an"),
        blank=True,
        help_text=_(
            "Z. B. sekretariat@meine-schule.de. Die Rolle „Sekretariat“ wird immer informiert."
        ),
    )

    class Visibility(models.TextChoices):
        TEAM = "team", _("nur Verwaltung und zuständiges Team")
        ALL = "all", _("alle angemeldeten Lehrkräfte")

    borrower_visibility = models.CharField(
        _("Wer sieht, bei wem etwas ausgeliehen ist?"),
        max_length=10,
        choices=Visibility,
        default=Visibility.TEAM,
        help_text=_(
            "„Alle“ erleichtert das direkte Nachfragen unter Kolleginnen und Kollegen. "
            "Die Übersicht aller Ausleihen bleibt immer der Verwaltung vorbehalten."
        ),
    )
    anonymous_lending = models.BooleanField(
        _("Ausleihen ohne Namen (nur Klasse oder Raum)"),
        default=False,
        help_text=_(
            "Z. B. bis zur Zustimmung des Personalrats. Beim Ausleihen wird statt der Person "
            "Klasse oder Raum erfasst; „Meine Ausleihen“ und Erinnerungen entfallen. "
            "Anfragen behalten den Namen bis zur Übergabe. Gilt nur für neue Ausleihen."
        ),
    )
    anonymize_after_days = models.PositiveSmallIntegerField(
        _("Namen aus abgeschlossenen Ausleihen entfernen nach … Tagen"),
        default=365,
        help_text=_(
            "Gilt für zurückgegebene, abgelehnte, zurückgezogene und verfallene Vorgänge. "
            "Datum, Titel und Exemplar bleiben für die Statistik."
        ),
    )
    history_names_days = models.PositiveSmallIntegerField(
        _("Im Änderungsprotokoll „wer“ entfernen nach … Tagen"),
        default=365,
        help_text=_("Was geändert wurde, bleibt; nur der Name der ändernden Person wird entfernt."),
    )
    last_privacy_run = models.DateTimeField(
        _("Datenschutz-Bereinigung zuletzt am"), null=True, blank=True
    )
    last_reminder_run = models.DateField(
        _("Erinnerungen zuletzt verschickt am"), null=True, blank=True
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
