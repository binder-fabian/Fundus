"""Aufbereitung des Änderungsprotokolls (django-simple-history) für die Anzeige."""

from django.db import models
from django.utils.translation import gettext_lazy as _

CHANGE_TYPES = {"+": _("angelegt"), "~": _("geändert"), "-": _("gelöscht")}


def _display(field, value):
    if value in (None, ""):
        return "–"
    if isinstance(field, models.ForeignKey):
        obj = field.related_model._default_manager.filter(pk=value).first()
        return str(obj) if obj else f"#{value}"
    if isinstance(field, models.ManyToManyField):
        names = []
        for entry in value:
            pk = entry.get(field.m2m_reverse_field_name()) if isinstance(entry, dict) else entry
            obj = field.related_model._default_manager.filter(pk=pk).first()
            names.append(str(obj) if obj else f"#{pk}")
        return ", ".join(sorted(names)) or "–"
    if isinstance(field, models.BooleanField):
        return _("ja") if value else _("nein")
    if field.choices:
        return dict(field.flatchoices).get(value, value)
    return str(value)


def history_entries(records):
    """Liste der Protokolleinträge, neueste zuerst, mit den geänderten Feldern."""
    entries = []
    for record in records.order_by("-history_date", "-history_id"):
        changes = []
        previous = record.prev_record
        if previous is not None and record.history_type == "~":
            delta = record.diff_against(previous)
            model = record.instance_type
            for change in delta.changes:
                field = model._meta.get_field(change.field)
                changes.append(
                    {
                        "field": field.verbose_name,
                        "old": _display(field, change.old),
                        "new": _display(field, change.new),
                    }
                )
        entries.append(
            {
                "record": record,
                "type": CHANGE_TYPES.get(record.history_type, record.history_type),
                "changes": changes,
            }
        )
    return entries
