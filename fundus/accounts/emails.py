import logging
import smtplib

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from fundus.accounts.tokens import invitation_token

logger = logging.getLogger(__name__)


def absolute_url(path):
    return settings.SITE_URL.rstrip("/") + path


def invitation_link(user):
    uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
    path = reverse("invitation_accept", args=[uidb64, invitation_token.make_token(user)])
    return absolute_url(path)


def send_invitation(user, invited_by=None):
    """Schickt die Einladung. Gibt False zurück, wenn der Versand scheitert,
    damit die Oberfläche einen Hinweis zeigen kann statt abzubrechen."""
    context = {
        "user": user,
        "invited_by": invited_by,
        "link": invitation_link(user),
        "days": settings.INVITATION_TIMEOUT_DAYS,
        "site_url": settings.SITE_URL,
    }
    subject = render_to_string("accounts/email/invitation_subject.txt", context).strip()
    body = render_to_string("accounts/email/invitation_body.txt", context)
    try:
        send_mail(subject, body, None, [user.email])
    except (smtplib.SMTPException, OSError):
        logger.exception("Einladung an %s konnte nicht verschickt werden", user.email)
        return False
    return True
