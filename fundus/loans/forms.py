from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from fundus.accounts.models import User
from fundus.catalog.forms import PersonChoiceField


class LendForm(forms.Form):
    due_date = forms.DateField(
        label=_("Rückgabe bis"), widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
    )
    borrower = PersonChoiceField(
        queryset=User.objects.filter(is_active=True).order_by("last_name", "first_name"),
        required=False,
        label=_("für"),
    )

    borrower_label = forms.CharField(
        label=_("für Klasse oder Raum"),
        max_length=100,
        widget=forms.TextInput(
            attrs={"list": "label-suggestions", "autocomplete": "off", "placeholder": "z. B. 3b"}
        ),
        help_text=_("Ausleihen werden ohne Namen erfasst."),
    )

    def __init__(self, *args, for_others=False, anonymous=False, **kwargs):
        super().__init__(*args, **kwargs)
        if anonymous or not for_others:
            del self.fields["borrower"]
        if not anonymous:
            del self.fields["borrower_label"]

    def clean_due_date(self):
        due = self.cleaned_data["due_date"]
        if due < timezone.localdate():
            raise forms.ValidationError(_("Das Datum liegt in der Vergangenheit."))
        return due


def contents_check(title, data):
    """Wertet die Inhalts-Checkliste aus: (vollständig?, fehlende Teile) oder (None, [])."""
    items = title.contents_items
    if not items:
        return None, []
    missing = [item for i, item in enumerate(items) if not data.get(f"part_{i}")]
    return not missing, missing


class RequestForm(forms.Form):
    wished_from = forms.DateField(
        label=_("gewünscht ab"),
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    wished_until = forms.DateField(
        label=_("gewünscht bis"),
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    message = forms.CharField(
        label=_("Nachricht an das Team"),
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": _("z. B. für welche Klasse")}),
    )


class _ReserveForm(forms.Form):
    quantity = forms.IntegerField(
        label=_("Anzahl Exemplare"), min_value=1, initial=1, required=False
    )
    borrower_label = forms.CharField(
        label=_("für Klasse oder Raum"),
        max_length=100,
        widget=forms.TextInput(
            attrs={"list": "label-suggestions", "autocomplete": "off", "placeholder": "z. B. 3b"}
        ),
    )

    def __init__(self, *args, capacity=1, anonymous=False, **kwargs):
        super().__init__(*args, **kwargs)
        if capacity <= 1:
            del self.fields["quantity"]
        else:
            self.fields["quantity"].max_value = capacity
            self.fields["quantity"].widget.attrs["max"] = capacity
        if not anonymous:
            del self.fields["borrower_label"]

    def _not_past(self, field):
        day = self.cleaned_data[field]
        if day < timezone.localdate():
            raise forms.ValidationError(_("Das Datum liegt in der Vergangenheit."))
        return day


class ReserveDaysForm(_ReserveForm):
    first = forms.DateField(
        label=_("von"), widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
    )
    last = forms.DateField(
        label=_("bis"), widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
    )
    field_order = ["first", "last", "quantity", "borrower_label"]

    def clean_first(self):
        return self._not_past("first")

    def clean(self):
        cleaned = super().clean()
        first, last = cleaned.get("first"), cleaned.get("last")
        if first and last and last < first:
            self.add_error("last", _("„Bis“ liegt vor „von“."))
        return cleaned


class ReserveLessonsForm(_ReserveForm):
    day = forms.DateField(
        label=_("Tag"), widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
    )
    first = forms.TypedChoiceField(label=_("von Stunde"), coerce=int)
    last = forms.TypedChoiceField(label=_("bis Stunde"), coerce=int)
    field_order = ["day", "first", "last", "quantity", "borrower_label"]

    def __init__(self, *args, lessons=(), **kwargs):
        super().__init__(*args, **kwargs)
        choices = [(n, f"{n}. ({start:%H:%M}–{end:%H:%M})") for n, start, end in lessons]
        self.fields["first"].choices = choices
        self.fields["last"].choices = choices

    def clean_day(self):
        return self._not_past("day")

    def clean(self):
        cleaned = super().clean()
        first, last = cleaned.get("first"), cleaned.get("last")
        if first and last and last < first:
            self.add_error("last", _("Die letzte Stunde liegt vor der ersten."))
        return cleaned
