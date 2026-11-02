"""Verbrauchsmaterial: Entnahme, Auffüllen, Nachbestellen."""

import logging
import re
import smtplib

from django.conf import settings
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext as _

from fundus.accounts.models import Role, User
from fundus.core.models import SchoolSettings
from fundus.supplies.models import Consumable, ReorderNotice

logger = logging.getLogger(__name__)

CODE_PREFIX = "NB-"


class SupplyError(Exception):
    pass


def next_code():
    numbers = [
        int(m.group(1))
        for c in Consumable.objects.filter(code__istartswith=CODE_PREFIX).values_list(
            "code", flat=True
        )
        if (m := re.fullmatch(re.escape(CODE_PREFIX) + r"(\d+)", c, re.IGNORECASE))
    ]
    return f"{CODE_PREFIX}{max(numbers, default=0) + 1:04d}"


def notice_recipients():
    emails = list(
        User.objects.filter(is_active=True, role=Role.SECRETARY)
        .exclude(email="")
        .values_list("email", flat=True)
    )
    extra = SchoolSettings.current().reorder_email
    if extra and extra not in emails:
        emails.append(extra)
    return emails


def _notify(notice):
    recipients = notice_recipients()
    if not recipients:
        return False
    with translation.override(settings.LANGUAGE_CODE):
        context = {
            "notice": notice,
            "item": notice.consumable,
            "link": settings.SITE_URL.rstrip("/") + reverse("reorder_list"),
        }
        subject = render_to_string("supplies/email/reorder_subject.txt", context).strip()
        body = render_to_string("supplies/email/reorder_body.txt", context)
    try:
        send_mail(subject, body, None, recipients)
    except (smtplib.SMTPException, OSError):
        logger.exception("Nachbestellhinweis an %s fehlgeschlagen", recipients)
        return False
    return True


@transaction.atomic
def request_reorder(item, by=None, reason=ReorderNotice.Reason.CARD):
    """Erzeugt einen Nachbestellhinweis. Gibt (hinweis, neu?) zurück; liegt
    schon ein offener Hinweis vor, wird kein zweiter angelegt."""
    existing = item.open_notice()
    if existing:
        return existing, False
    try:
        with transaction.atomic():
            notice = ReorderNotice.objects.create(consumable=item, created_by=by, reason=reason)
    except IntegrityError:
        return item.open_notice(), False
    _notify(notice)
    return notice, True


@transaction.atomic
def take(item, by, quantity=1):
    """Entnahme buchen; erreicht der Bestand die Mindestmenge, wird nachbestellt."""
    item = Consumable.objects.select_for_update().get(pk=item.pk)
    if not item.track_stock:
        raise SupplyError(_("Für dieses Material wird kein Bestand gezählt."))
    if quantity < 1:
        raise SupplyError(_("Bitte eine Menge ab 1 angeben."))
    item.stock = max(0, item.stock - quantity)
    item._change_reason = f"Entnahme {quantity}"
    item.save()
    notice = None
    if item.below_minimum:
        notice, _created = request_reorder(item, by=by, reason=ReorderNotice.Reason.MINIMUM)
    return item, notice


@transaction.atomic
def restock(item, by, quantity):
    item = Consumable.objects.select_for_update().get(pk=item.pk)
    if quantity < 1:
        raise SupplyError(_("Bitte eine Menge ab 1 angeben."))
    item.stock += quantity
    item._change_reason = f"Aufgefüllt {quantity}"
    item.save()
    return item


def _check_handler(by):
    if not by.can_handle_orders:
        raise SupplyError(_("Nachbestellungen bearbeitet das Sekretariat."))


@transaction.atomic
def mark_ordered(notice, by):
    _check_handler(by)
    notice = ReorderNotice.objects.select_for_update().get(pk=notice.pk)
    if notice.status != ReorderNotice.Status.OPEN:
        raise SupplyError(_("Dieser Hinweis ist nicht mehr offen."))
    notice.status = ReorderNotice.Status.ORDERED
    notice.ordered_at = timezone.now()
    notice.handled_by = by
    notice.save()
    return notice


@transaction.atomic
def mark_delivered(notice, by, quantity=None):
    _check_handler(by)
    notice = ReorderNotice.objects.select_for_update().get(pk=notice.pk)
    if notice.status not in ReorderNotice.OPEN:
        raise SupplyError(_("Dieser Hinweis ist schon erledigt."))
    notice.status = ReorderNotice.Status.DELIVERED
    notice.delivered_at = timezone.now()
    notice.handled_by = by
    notice.quantity_delivered = quantity
    notice.save()
    if quantity and notice.consumable.track_stock:
        restock(notice.consumable, by, quantity)
    return notice


@transaction.atomic
def cancel(notice, by):
    _check_handler(by)
    notice = ReorderNotice.objects.select_for_update().get(pk=notice.pk)
    if notice.status not in ReorderNotice.OPEN:
        raise SupplyError(_("Dieser Hinweis ist schon erledigt."))
    notice.status = ReorderNotice.Status.CANCELLED
    notice.handled_by = by
    notice.save()
    return notice
