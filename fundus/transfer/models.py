from django.db import models
from django.utils.translation import gettext_lazy as _

from fundus.core.models import SchoolScopedModel


class ImportTemplate(SchoolScopedModel):
    """Gespeicherte Spaltenzuordnung, z. B. für den Export einer Microsoft List."""

    name = models.CharField(_("Name"), max_length=100)
    mapping = models.JSONField(_("Zuordnung"), default=dict)
    created_at = models.DateTimeField(_("angelegt am"), auto_now_add=True)

    class Meta:
        verbose_name = _("Importvorlage")
        verbose_name_plural = _("Importvorlagen")
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["school", "name"], name="importtemplate_unique_name"),
        ]

    def __str__(self):
        return self.name
