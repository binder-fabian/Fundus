from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AccountsConfig(AppConfig):
    name = "fundus.accounts"
    verbose_name = _("Benutzer")

    def ready(self):
        from django.contrib.auth.signals import user_logged_in, user_login_failed

        from fundus.accounts import throttle

        def on_failure(sender, credentials, request=None, **kwargs):
            throttle.record_failure(credentials.get("username", ""), request)

        def on_success(sender, request, user, **kwargs):
            throttle.clear(user.email)

        user_login_failed.connect(on_failure, weak=False, dispatch_uid="fundus_login_failed")
        user_logged_in.connect(on_success, weak=False, dispatch_uid="fundus_logged_in")
