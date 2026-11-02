from django.conf import settings
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from fundus.catalog.models import Location, Title
from fundus.core.models import SchoolScopedModel


class Consumable(SchoolScopedModel):
    """Verbrauchsmaterial, z. B. Protokollbögen zu einem Test."""

    name = models.CharField(_("Bezeichnung"), max_length=200)
    code = models.CharField(
        _("Kennung"),
        max_length=30,
        help_text=_("Steht im QR-Code der Nachbestellkarte, z. B. NB-0001."),
    )
    title = models.ForeignKey(
        Title,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="consumables",
        verbose_name=_("gehört zu"),
    )
    location = models.ForeignKey(
        Location,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="consumables",
        verbose_name=_("Standort"),
    )
    unit = models.CharField(_("Einheit"), max_length=30, default="Stück")
    track_stock = models.BooleanField(
        _("Bestand zählen"),
        default=False,
        help_text=_("Sonst wird nur über die Nachbestellkarte nachbestellt."),
    )
    stock = models.PositiveIntegerField(_("Bestand"), default=0)
    min_stock = models.PositiveIntegerField(
        _("Mindestmenge"),
        default=0,
        help_text=_("Wird sie erreicht oder unterschritten, geht ein Nachbestellhinweis raus."),
    )
    order_info = models.TextField(
        _("Bestellhinweis"),
        blank=True,
        help_text=_("Lieferant, Artikelnummer, Packungsgröße …"),
    )
    note = models.TextField(_("Notiz"), blank=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name = _("Verbrauchsmaterial")
        verbose_name_plural = _("Verbrauchsmaterial")
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint("school", Lower("code"), name="consumable_unique_code"),
        ]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("consumable_detail", args=[self.pk])

    @property
    def below_minimum(self):
        return self.track_stock and self.stock <= self.min_stock

    def open_notice(self):
        return self.notices.filter(status__in=ReorderNotice.OPEN).first()


class ReorderNotice(models.Model):
    """Nachbestellhinweis an das Sekretariat."""

    class Status(models.TextChoices):
        OPEN = "open", _("offen")
        ORDERED = "ordered", _("bestellt")
        DELIVERED = "delivered", _("geliefert")
        CANCELLED = "cancelled", _("verworfen")

    class Reason(models.TextChoices):
        CARD = "card", _("Nachbestellkarte gescannt")
        MINIMUM = "minimum", _("Mindestmenge erreicht")
        MANUAL = "manual", _("von Hand")

    OPEN = (Status.OPEN, Status.ORDERED)

    consumable = models.ForeignKey(
        Consumable, on_delete=models.CASCADE, related_name="notices", verbose_name=_("Material")
    )
    status = models.CharField(_("Status"), max_length=20, choices=Status, default=Status.OPEN)
    reason = models.CharField(_("Anlass"), max_length=20, choices=Reason, default=Reason.CARD)
    created_at = models.DateTimeField(_("gemeldet am"), auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("gemeldet von"),
    )
    ordered_at = models.DateTimeField(_("bestellt am"), null=True, blank=True)
    delivered_at = models.DateTimeField(_("geliefert am"), null=True, blank=True)
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("bearbeitet von"),
    )
    quantity_delivered = models.PositiveIntegerField(_("gelieferte Menge"), null=True, blank=True)

    class Meta:
        verbose_name = _("Nachbestellhinweis")
        verbose_name_plural = _("Nachbestellhinweise")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["consumable"],
                condition=Q(status__in=["open", "ordered"]),
                name="reorder_one_open_per_consumable",
            ),
        ]

    def __str__(self):
        return f"{self.consumable} ({self.get_status_display()})"
