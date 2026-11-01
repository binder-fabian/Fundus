from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from fundus.catalog.models import Copy


class Loan(models.Model):
    """Ausleihprotokoll: ein Eintrag pro Vorgang.

    Ob ein Exemplar ausgeliehen ist, ergibt sich allein aus diesen Einträgen
    (siehe `Copy.objects.with_availability()`).
    """

    class Status(models.TextChoices):
        REQUESTED = "requested", _("angefragt")
        APPROVED = "approved", _("genehmigt")
        LENT = "lent", _("ausgeliehen")
        RETURNED = "returned", _("zurück")
        REJECTED = "rejected", _("abgelehnt")

    copy = models.ForeignKey(
        Copy, on_delete=models.PROTECT, related_name="loans", verbose_name=_("Exemplar")
    )
    # Personenbezug: entweder eine Lehrkraft oder – im Modus ohne Personenbezug –
    # nur Klasse/Raum. Nach Ablauf der Löschfrist wird beides entfernt (anonymized_at).
    borrower = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="loans",
        verbose_name=_("Lehrkraft"),
    )
    borrower_label = models.CharField(
        _("Klasse oder Raum"),
        max_length=100,
        blank=True,
        help_text=_("Statt einer Lehrkraft, wenn ohne Personenbezug ausgeliehen wird."),
    )
    status = models.CharField(_("Status"), max_length=20, choices=Status, default=Status.REQUESTED)
    lent_at = models.DateTimeField(_("ausgeliehen am"), null=True, blank=True)
    due_date = models.DateField(_("Rückgabe geplant am"), null=True, blank=True)
    returned_at = models.DateTimeField(_("zurückgegeben am"), null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("genehmigt von"),
    )
    handed_over_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("übergeben von"),
    )
    anonymized_at = models.DateTimeField(_("anonymisiert am"), null=True, blank=True)
    created_at = models.DateTimeField(_("angelegt am"), auto_now_add=True)
    updated_at = models.DateTimeField(_("geändert am"), auto_now=True)

    # Hinweis für Phase 5: Die Anonymisierung muss auch die Historie bereinigen.
    history = HistoricalRecords()

    class Meta:
        verbose_name = _("Ausleihe")
        verbose_name_plural = _("Ausleihen")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["copy"],
                condition=Q(status="lent"),
                name="loan_one_active_per_copy",
                violation_error_message=_("Dieses Exemplar ist bereits ausgeliehen."),
            ),
            models.CheckConstraint(
                condition=(
                    Q(borrower__isnull=False)
                    | ~Q(borrower_label="")
                    | Q(anonymized_at__isnull=False)
                ),
                name="loan_has_borrower_or_label",
                violation_error_message=_("Lehrkraft oder Klasse/Raum angeben."),
            ),
            models.CheckConstraint(
                condition=~Q(status__in=["lent", "returned"]) | Q(lent_at__isnull=False),
                name="loan_lent_has_lent_at",
            ),
            models.CheckConstraint(
                condition=~Q(status="returned") | Q(returned_at__isnull=False),
                name="loan_returned_has_returned_at",
            ),
        ]

    def __str__(self):
        return f"{self.copy.inventory_number} ({self.get_status_display()})"

    @property
    def borrower_display(self):
        if self.anonymized_at:
            return _("anonymisiert")
        return str(self.borrower) if self.borrower else self.borrower_label
