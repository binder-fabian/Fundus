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

    def __init__(self, *args, for_others=False, **kwargs):
        super().__init__(*args, **kwargs)
        if not for_others:
            del self.fields["borrower"]

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
