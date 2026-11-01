from django.conf import settings
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.crypto import constant_time_compare
from django.utils.http import base36_to_int


class InvitationTokenGenerator(PasswordResetTokenGenerator):
    """Einmal-Link für Einladungen. Wird ungültig, sobald ein Passwort gesetzt
    ist, und läuft nach INVITATION_TIMEOUT_DAYS ab (länger als ein
    Passwort-Reset, weil Einladungen oft erst nach Tagen gelesen werden)."""

    key_salt = "fundus.accounts.tokens.InvitationTokenGenerator"

    def check_token(self, user, token):
        if not (user and token):
            return False
        try:
            ts_b36, _hash = token.split("-")
            ts = base36_to_int(ts_b36)
        except ValueError:
            return False
        for secret in [self.secret, *self.secret_fallbacks]:
            if constant_time_compare(self._make_token_with_timestamp(user, ts, secret), token):
                break
        else:
            return False
        timeout = settings.INVITATION_TIMEOUT_DAYS * 24 * 3600
        return (self._num_seconds(self._now()) - ts) <= timeout


invitation_token = InvitationTokenGenerator()
