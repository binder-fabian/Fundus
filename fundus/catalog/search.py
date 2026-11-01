"""Katalogsuche.

Gesucht wird in einem normalisierten Suchtext je Titel (siehe `text.py`). So
verhält sich die Suche in SQLite und PostgreSQL gleich – SQLite vergleicht
Umlaute sonst mit Beachtung der Groß-/Kleinschreibung.
"""

from django import forms
from django.db.models import Count, Exists, F, OuterRef, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from fundus.catalog.models import Category, Copy, Location, SupportFocus, Title
from fundus.catalog.text import normalize
from fundus.core.models import SchoolSettings
from fundus.loans.models import Loan


class CatalogFilterForm(forms.Form):
    AVAILABLE = "verfuegbar"
    LENT = "ausgeliehen"

    q = forms.CharField(
        label=_("Suche"),
        required=False,
        widget=forms.TextInput(
            attrs={
                "type": "search",
                "placeholder": _("Titel, Autor, ISBN oder Inventarnummer"),
                "autocomplete": "off",
            }
        ),
    )
    kategorie = forms.ModelChoiceField(
        Category.objects.all(), required=False, label=_("Kategorie"), empty_label=_("alle")
    )
    foerderschwerpunkt = forms.ModelChoiceField(
        SupportFocus.objects.all(),
        required=False,
        label=_("Förderschwerpunkt"),
        empty_label=_("alle"),
    )
    standort = forms.ModelChoiceField(
        Location.objects.all(), required=False, label=_("Standort"), empty_label=_("alle")
    )
    verfuegbarkeit = forms.ChoiceField(
        required=False,
        label=_("Verfügbarkeit"),
        choices=[
            ("", _("alle")),
            (AVAILABLE, _("verfügbar")),
            (LENT, _("ausgeliehen")),
        ],
    )
    veraltet = forms.BooleanField(required=False, label=_("nur veraltete Tests"))


def outdated_before_year():
    """Tests mit Normjahr vor diesem Jahr gelten als veraltet."""
    return timezone.localdate().year - SchoolSettings.current().outdated_norm_years


def annotated_titles():
    lent = Q(copies__loans__status=Loan.Status.LENT)
    return (
        Title.objects.select_related("category")
        .annotate(
            copy_count=Count("copies", distinct=True),
            lent_count=Count("copies__loans", filter=lent, distinct=True),
        )
        .annotate(available_count=F("copy_count") - F("lent_count"))
    )


def search_titles(data):
    form = CatalogFilterForm(data)
    titles = annotated_titles()
    if not form.is_valid():
        return form, titles.order_by("title")
    cleaned = form.cleaned_data

    for word in cleaned["q"].split():
        number_match = Copy.objects.filter(title=OuterRef("pk"), inventory_number__icontains=word)
        titles = titles.filter(
            Q(search_text__contains=normalize(word))
            | Q(search_text__contains=normalize(word.replace("-", "")))
            | Exists(number_match)
        )
    if cleaned["kategorie"]:
        titles = titles.filter(category=cleaned["kategorie"])
    if cleaned["foerderschwerpunkt"]:
        titles = titles.filter(support_focuses=cleaned["foerderschwerpunkt"])
    if cleaned["standort"]:
        titles = titles.filter(
            Exists(Copy.objects.filter(title=OuterRef("pk"), location=cleaned["standort"]))
        )
    if cleaned["verfuegbarkeit"] == CatalogFilterForm.AVAILABLE:
        titles = titles.filter(lendable=True, available_count__gt=0)
    elif cleaned["verfuegbarkeit"] == CatalogFilterForm.LENT:
        titles = titles.filter(lent_count__gt=0)
    if cleaned["veraltet"]:
        titles = titles.filter(norm_year__lt=outdated_before_year())
    return form, titles.order_by("title")


def exact_copy(query):
    """Exemplar, dessen Inventarnummer genau der Eingabe entspricht (Scanner)."""
    query = (query or "").strip()
    if not query or " " in query:
        return None
    return Copy.objects.filter(inventory_number__iexact=query).first()
