from django.db import models
from django.utils.translation import gettext_lazy as _


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
