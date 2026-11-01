from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class TransferConfig(AppConfig):
    name = "fundus.transfer"
    verbose_name = _("Import und Export")
