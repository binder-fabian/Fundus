from django.core.validators import MinValueValidator
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


DEFAULT_LESSON_TIMES = "\n".join(
    [
        "08:00-08:45",
        "08:45-09:30",
        "09:45-10:30",
        "10:30-11:15",
        "11:30-12:15",
        "12:15-13:00",
        "13:15-14:00",
        "14:00-14:45",
    ]
)


def parse_day_month(text):
    """„1.8.“, „01.08.“ oder „01.08“ → (Monat, Tag). Wirft ValueError."""
    import datetime
    import re

    match = re.fullmatch(r"\s*(\d{1,2})\.(\d{1,2})\.?\s*", text or "")
    if not match:
        raise ValueError(_("Bitte Tag und Monat angeben, z. B. 01.08."))
    day, month = int(match.group(1)), int(match.group(2))
    try:
        # 2025 ist kein Schaltjahr: der 29.02. ist als Stichtag nicht erlaubt.
        datetime.date(2025, month, day)
    except ValueError:
        raise ValueError(_("Diesen Tag gibt es nicht in jedem Jahr.")) from None
    return month, day


def parse_lesson_times(text):
    """„08:00-08:45“ je Zeile → [(1, time(8, 0), time(8, 45)), …]. Wirft ValueError."""
    import datetime
    import re

    lessons = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        match = re.fullmatch(r"(\d{1,2})[:.](\d{2})\s*[-–]\s*(\d{1,2})[:.](\d{2})", line)
        if not match:
            raise ValueError(_("Zeile „%(l)s“: bitte im Format 08:00-08:45.") % {"l": line})
        h1, m1, h2, m2 = map(int, match.groups())
        try:
            start, end = datetime.time(h1, m1), datetime.time(h2, m2)
        except ValueError:
            raise ValueError(_("Zeile „%(l)s“: keine gültige Uhrzeit.") % {"l": line}) from None
        if end <= start:
            raise ValueError(_("Zeile „%(l)s“: Ende liegt vor dem Beginn.") % {"l": line})
        if lessons and start < lessons[-1][2]:
            raise ValueError(
                _("Zeile „%(l)s“ beginnt vor dem Ende der vorigen Stunde.") % {"l": line}
            )
        lessons.append((len(lessons) + 1, start, end))
    return lessons


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
    school_year_start = models.CharField(
        _("Schuljahr beginnt am"),
        max_length=6,
        default="01.08.",
        help_text=_("Tag und Monat, z. B. „01.08.“. Für die Zeiträume in der Statistik."),
    )
    second_half_start = models.CharField(
        _("2. Halbjahr beginnt am"),
        max_length=6,
        default="01.02.",
        help_text=_("Tag und Monat, z. B. „01.02.“ oder „15.02.“."),
    )
    lesson_times = models.TextField(
        _("Stundenraster"),
        default=DEFAULT_LESSON_TIMES,
        help_text=_(
            "Eine Zeile pro Unterrichtsstunde mit Beginn und Ende, z. B. „08:00-08:45“. "
            "Die erste Zeile ist die 1. Stunde."
        ),
    )
    reservation_reminders = models.BooleanField(
        _("Erinnerung an Reservierungen"),
        default=True,
        help_text=_(
            "Am Vortag eine E-Mail an die Person, die reserviert hat, und ein Hinweis am "
            "ersten Tag, falls noch nicht abgeholt."
        ),
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

    class BackupInterval(models.TextChoices):
        OFF = "off", _("aus")
        DAILY = "daily", _("täglich")
        WEEKLY = "weekly", _("wöchentlich")
        MONTHLY = "monthly", _("monatlich")

    backup_interval = models.CharField(
        _("Automatische Sicherung"),
        max_length=10,
        choices=BackupInterval,
        default=BackupInterval.DAILY,
    )
    backup_keep = models.PositiveSmallIntegerField(
        _("Anzahl aufbewahrter Sicherungen"),
        default=14,
        validators=[MinValueValidator(1)],
        help_text=_(
            "Ältere werden automatisch gelöscht. Bis dahin stehen auch Namen darin, "
            "die in Fundus selbst schon anonymisiert sind."
        ),
    )

    class PasswordLogin(models.TextChoices):
        ALL = "all", _("für alle")
        ADMINS = "admins", _("nur für Administratoren (Notzugang)")

    sso_create_accounts = models.BooleanField(
        _("Neue Konten bei der ersten Anmeldung mit Schulkonto automatisch anlegen"),
        default=False,
        help_text=_(
            "Aus: Nur wer schon ein Konto in Fundus hat (z. B. per Import), kann sich "
            "anmelden; andere bekommen „Bitte an die Verwaltung wenden“. An: Neue Personen "
            "werden als Lehrkraft angelegt."
        ),
    )
    sso_domains = models.CharField(
        _("Automatisch anlegen nur für diese E-Mail-Domains"),
        max_length=300,
        blank=True,
        help_text=_("Z. B. „meine-schule.de“; mehrere mit Komma trennen. Leer = alle."),
    )
    password_login = models.CharField(
        _("Anmeldung mit Fundus-Passwort"),
        max_length=10,
        choices=PasswordLogin,
        default=PasswordLogin.ALL,
        help_text=_(
            "Gilt nur, wenn die Anmeldung mit Schulkonto eingerichtet ist. Administratoren "
            "behalten ihr Passwort immer als Notzugang."
        ),
    )

    last_backup_at = models.DateTimeField(_("letzte Sicherung"), null=True, blank=True)
    last_backup_error = models.TextField(_("Fehler bei der letzten Sicherung"), blank=True)
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

    @property
    def lessons(self):
        try:
            return parse_lesson_times(self.lesson_times)
        except ValueError:
            return parse_lesson_times(DEFAULT_LESSON_TIMES)

    @property
    def school_year_dates(self):
        """(Monat, Tag) für Schuljahresbeginn und 2. Halbjahr, notfalls Standard."""
        try:
            return parse_day_month(self.school_year_start), parse_day_month(self.second_half_start)
        except ValueError:
            return (8, 1), (2, 1)

    def domain_allowed(self, email):
        domains = [d.strip().lower().lstrip("@") for d in self.sso_domains.split(",") if d.strip()]
        return not domains or email.rsplit("@", 1)[-1].lower() in domains

    def format_number(self, number):
        return f"{self.number_prefix}{number:0{self.number_digits}d}"
