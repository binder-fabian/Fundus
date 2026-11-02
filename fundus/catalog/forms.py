import io
import re

from django import forms
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _
from PIL import Image, ImageOps

from fundus.accounts.models import User
from fundus.catalog import isbn_lookup, numbering
from fundus.catalog.models import Category, Copy, Location, SupportFocus, Team, Title

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
    cover_url = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = Title
        fields = [
            "isbn",
            "title",
            "subtitle",
            "author",
            "publisher",
            "edition",
            "category",
            "support_focuses",
            "description",
            "cover",
            "norm_year",
            "contents",
            "lendable",
            "approval_required",
            "team",
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
            if not cleaned.get("team"):
                self.add_error("team", _("Freigabepflichtige Titel brauchen ein zuständiges Team."))
        return cleaned

    def save(self, commit=True):
        cover = self.cleaned_data.get("cover")
        if cover and cover is not self.initial.get("cover") and hasattr(cover, "content_type"):
            self.instance.cover = shrink_cover(cover)
        elif not self.instance.cover and self.cleaned_data.get("cover_url"):
            data = isbn_lookup.download_cover(self.cleaned_data["cover_url"])
            if data:
                self.instance.cover = shrink_cover(io.BytesIO(data))
        return super().save(commit)

    def initial_from_lookup(self, data, result):
        """Füllt leere Felder mit den abgerufenen Daten (ohne zu speichern)."""
        found = dict(result.data)
        edition = ", ".join(v for v in (found.pop("edition", ""), found.pop("year", "")) if v)
        if edition:
            found["edition"] = edition
        filled = []
        for key, value in found.items():
            if key in self.fields and not data.get(key):
                data[key] = value
                filled.append(self.fields[key].label)
        if result.cover_url:
            data["cover_url"] = result.cover_url
        return filled


class CopiesAddForm(forms.Form):
    """Mehrere Exemplare eines Titels in einem Schritt anlegen: entweder eine
    Liste von Inventarnummern oder Präfix + Startnummer + Anzahl."""

    auto_count = forms.IntegerField(
        label=_("Anzahl (Nummern automatisch)"),
        required=False,
        min_value=1,
        max_value=200,
        help_text=_("Vergibt die nächsten freien Nummern nach dem Nummernschema."),
    )
    numbers = forms.CharField(
        label=_("oder eigene Inventarnummern"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "FS-0101\nFS-0102"}),
        help_text=_("Eine pro Zeile – oder darunter eine Nummernfolge erzeugen lassen."),
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
        if title is not None:
            self.fields["auto_count"].help_text = _(
                "Vergibt die nächsten freien Nummern nach dem Nummernschema, beginnend mit %(n)s."
            ) % {"n": numbering.preview_next(title.category)}
        else:
            self.fields["auto_count"].help_text = _(
                "Vergibt die nächsten freien Nummern nach dem Präfix der gewählten Kategorie."
            )

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

        auto_count = cleaned.get("auto_count")
        if auto_count and numbers:
            raise forms.ValidationError(
                _("Entweder automatische Nummern oder eigene Nummern angeben, nicht beides.")
            )
        if auto_count:
            cleaned["inventory_numbers"] = []
            return cleaned

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

    @transaction.atomic
    def save(self, title):
        numbers = list(self.cleaned_data["inventory_numbers"])
        if self.cleaned_data.get("auto_count"):
            numbers += numbering.allocate(self.cleaned_data["auto_count"], title.category)
        return [
            Copy.objects.create(
                title=title, inventory_number=n, location=self.cleaned_data.get("location")
            )
            for n in numbers
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
        fields = ["name", "default_loan_days", "number_prefix"]

    def clean_number_prefix(self):
        prefix = self.cleaned_data["number_prefix"].strip()
        if any(c.isspace() for c in prefix):
            raise forms.ValidationError(_("Das Präfix darf keine Leerzeichen enthalten."))
        return prefix


class SupportFocusForm(UniqueNameMixin, forms.ModelForm):
    class Meta:
        model = SupportFocus
        fields = ["name"]


class TeamForm(UniqueNameMixin, forms.ModelForm):
    members = forms.ModelMultipleChoiceField(
        queryset=User.objects.filter(is_active=True).order_by("last_name", "first_name"),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label=_("Mitglieder"),
    )

    class Meta:
        model = Team
        fields = ["name", "members"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["members"].label_from_instance = lambda u: u.get_full_name() or u.email


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
