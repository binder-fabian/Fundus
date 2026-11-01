import io
import re

from django import forms
from django.core.files.base import ContentFile
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _
from PIL import Image, ImageOps

from fundus.accounts.models import User
from fundus.catalog.models import Category, Copy, Location, SupportFocus, Title

COVER_MAX_SIZE = (600, 600)


def shrink_cover(upload):
    """Verkleinert ein hochgeladenes Coverbild und speichert es als JPEG."""
    image = ImageOps.exif_transpose(Image.open(upload))
    image.thumbnail(COVER_MAX_SIZE)
    if image.mode != "RGB":
        image = image.convert("RGB")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=85, optimize=True)
    return ContentFile(buffer.getvalue(), name="cover.jpg")


class PersonChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.get_full_name() or obj.email}"


class TitleForm(forms.ModelForm):
    responsible = PersonChoiceField(
        queryset=User.objects.filter(is_active=True), required=False, label=_("zuständige Person")
    )
    deputy = PersonChoiceField(
        queryset=User.objects.filter(is_active=True), required=False, label=_("Vertretung")
    )

    class Meta:
        model = Title
        fields = [
            "title",
            "subtitle",
            "author",
            "publisher",
            "isbn",
            "edition",
            "category",
            "support_focuses",
            "description",
            "cover",
            "norm_year",
            "contents",
            "lendable",
            "approval_required",
            "responsible",
            "deputy",
        ]
        widgets = {
            "support_focuses": forms.CheckboxSelectMultiple,
            "description": forms.Textarea(attrs={"rows": 4}),
            "contents": forms.Textarea(attrs={"rows": 4}),
            "cover": forms.ClearableFileInput(attrs={"accept": "image/*"}),
        }

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("approval_required"):
            if not cleaned.get("lendable"):
                self.add_error(
                    "approval_required", _("Freigabepflichtige Titel müssen ausleihbar sein.")
                )
            if not cleaned.get("responsible"):
                self.add_error(
                    "responsible", _("Freigabepflichtige Titel brauchen eine zuständige Person.")
                )
        return cleaned

    def save(self, commit=True):
        cover = self.cleaned_data.get("cover")
        if cover and cover is not self.initial.get("cover") and hasattr(cover, "content_type"):
            self.instance.cover = shrink_cover(cover)
        return super().save(commit)


class CopiesAddForm(forms.Form):
    """Mehrere Exemplare eines Titels in einem Schritt anlegen: entweder eine
    Liste von Inventarnummern oder Präfix + Startnummer + Anzahl."""

    numbers = forms.CharField(
        label=_("Inventarnummern"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "FS-0101\nFS-0102"}),
        help_text=_("Eine pro Zeile – oder unten eine Nummernfolge erzeugen lassen."),
    )
    prefix = forms.CharField(label=_("Präfix"), required=False, max_length=20)
    start = forms.CharField(
        label=_("Startnummer"),
        required=False,
        max_length=10,
        help_text=_("Führende Nullen bleiben erhalten, z. B. 0101."),
    )
    count = forms.IntegerField(label=_("Anzahl"), required=False, min_value=1, max_value=200)
    location = forms.ModelChoiceField(
        queryset=Location.objects.all(), required=False, label=_("Standort")
    )

    def __init__(self, *args, title=None, required=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.title = title
        self.required = required

    def clean(self):
        cleaned = super().clean()
        numbers = [n.strip() for n in cleaned.get("numbers", "").splitlines() if n.strip()]
        start, count = cleaned.get("start", "").strip(), cleaned.get("count")
        if start or count:
            if not (start.isdigit() and count):
                raise forms.ValidationError(
                    _("Für eine Nummernfolge Startnummer (nur Ziffern) und Anzahl angeben.")
                )
            width = len(start)
            prefix = cleaned.get("prefix", "").strip()
            numbers += [f"{prefix}{int(start) + i:0{width}d}" for i in range(count)]

        if not numbers:
            if self.required:
                raise forms.ValidationError(_("Bitte mindestens eine Inventarnummer angeben."))
            cleaned["inventory_numbers"] = []
            return cleaned

        lowered = [n.lower() for n in numbers]
        duplicates = sorted({n for n in numbers if lowered.count(n.lower()) > 1})
        if duplicates:
            raise forms.ValidationError(
                _("Doppelt eingegeben: %(numbers)s") % {"numbers": ", ".join(duplicates)}
            )
        taken = list(
            Copy.objects.annotate(lowered=Lower("inventory_number"))
            .filter(lowered__in=lowered)
            .values_list("inventory_number", flat=True)
        )
        if taken:
            raise forms.ValidationError(
                _("Schon vergeben: %(numbers)s") % {"numbers": ", ".join(sorted(set(taken)))}
            )
        too_long = [n for n in numbers if len(n) > 50 or not re.fullmatch(r"\S+", n)]
        if too_long:
            raise forms.ValidationError(
                _("Ungültig (Leerzeichen oder länger als 50 Zeichen): %(numbers)s")
                % {"numbers": ", ".join(too_long)}
            )
        cleaned["inventory_numbers"] = numbers
        return cleaned

    def save(self, title):
        return [
            Copy.objects.create(
                title=title, inventory_number=n, location=self.cleaned_data.get("location")
            )
            for n in self.cleaned_data["inventory_numbers"]
        ]


class CopyForm(forms.ModelForm):
    class Meta:
        model = Copy
        fields = ["inventory_number", "location", "condition", "incomplete", "note"]
        widgets = {"note": forms.Textarea(attrs={"rows": 3})}

    def clean_inventory_number(self):
        number = self.cleaned_data["inventory_number"].strip()
        clash = Copy.objects.filter(inventory_number__iexact=number).exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError(_("Diese Inventarnummer ist schon vergeben."))
        return number


class UniqueNameMixin:
    """Die Eindeutigkeit je Schule prüft die Datenbank; hier eine verständliche Meldung."""

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        model = self._meta.model
        if model.objects.filter(name__iexact=name).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError(_("Diesen Namen gibt es schon."))
        return name


class CategoryForm(UniqueNameMixin, forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "default_loan_days"]


class SupportFocusForm(UniqueNameMixin, forms.ModelForm):
    class Meta:
        model = SupportFocus
        fields = ["name"]


class LocationForm(forms.ModelForm):
    class Meta:
        model = Location
        fields = ["room", "shelf", "note"]

    def clean(self):
        cleaned = super().clean()
        room, shelf = cleaned.get("room", "").strip(), cleaned.get("shelf", "").strip()
        clash = Location.objects.filter(room__iexact=room, shelf__iexact=shelf)
        if room and clash.exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError(_("Diesen Standort gibt es schon."))
        return cleaned
