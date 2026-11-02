from django import forms
from django.utils.translation import gettext_lazy as _

from fundus.supplies.models import Consumable


class ConsumableForm(forms.ModelForm):
    class Meta:
        model = Consumable
        fields = [
            "name",
            "code",
            "title",
            "location",
            "unit",
            "track_stock",
            "stock",
            "min_stock",
            "order_info",
            "note",
        ]
        widgets = {
            "order_info": forms.Textarea(attrs={"rows": 3}),
            "note": forms.Textarea(attrs={"rows": 2}),
        }

    def clean_code(self):
        code = self.cleaned_data["code"].strip()
        if any(c.isspace() for c in code):
            raise forms.ValidationError(_("Die Kennung darf keine Leerzeichen enthalten."))
        clash = Consumable.objects.filter(code__iexact=code).exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError(_("Diese Kennung ist schon vergeben."))
        return code


class QuantityForm(forms.Form):
    quantity = forms.IntegerField(label=_("Menge"), min_value=1, max_value=10000, initial=1)


class CardsForm(forms.Form):
    items = forms.ModelMultipleChoiceField(
        Consumable.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label=_("Karten für"),
    )
