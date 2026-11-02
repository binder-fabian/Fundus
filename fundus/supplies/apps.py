from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class SuppliesConfig(AppConfig):
    name = "fundus.supplies"
    verbose_name = _("Verbrauchsmaterial")
