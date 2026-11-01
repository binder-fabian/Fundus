from django import forms
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from fundus.accounts.permissions import require
from fundus.catalog import labels
from fundus.catalog.models import Category, Copy, Location, Title
from fundus.core.models import School, SchoolSettings, default_school_id

SELECTIONS = [
    ("neu", gettext_lazy("noch nicht gedruckte Exemplare")),
    ("kategorie", gettext_lazy("alle Exemplare einer Kategorie")),
    ("standort", gettext_lazy("alle Exemplare an einem Standort")),
    ("titel", gettext_lazy("alle Exemplare eines Titels")),
    ("exemplar", gettext_lazy("einzelne Exemplare")),
    ("alle", gettext_lazy("alle Exemplare")),
]


class LabelForm(forms.Form):
    auswahl = forms.ChoiceField(label=gettext_lazy("Welche Etiketten?"), choices=SELECTIONS)
    kategorie = forms.ModelChoiceField(
        Category.objects.all(), required=False, label=gettext_lazy("Kategorie")
    )
    standort = forms.ModelChoiceField(
        Location.objects.all(), required=False, label=gettext_lazy("Standort")
    )
    titel = forms.ModelChoiceField(Title.objects.all(), required=False, widget=forms.HiddenInput)
    exemplar = forms.ModelMultipleChoiceField(
        Copy.objects.all(), required=False, widget=forms.MultipleHiddenInput
    )
    format = forms.ChoiceField(
        label=gettext_lazy("Etikettenbogen"),
        choices=[(f.code, f.label) for f in labels.FORMATS.values()],
        initial=labels.DEFAULT_FORMAT,
    )
    start = forms.IntegerField(
        label=gettext_lazy("Beginnen bei Etikett Nr."),
        min_value=1,
        max_value=80,
        initial=1,
        help_text=gettext_lazy(
            "Für angebrochene Bögen: Etiketten werden zeilenweise von links oben gezählt."
        ),
    )

    def clean(self):
        cleaned = super().clean()
        needed = {"kategorie": "kategorie", "standort": "standort", "titel": "titel"}
        field = needed.get(cleaned.get("auswahl"))
        if field and not cleaned.get(field):
            self.add_error(field if field != "titel" else None, _("Bitte auswählen."))
        fmt = labels.FORMATS.get(cleaned.get("format"))
        if fmt and cleaned.get("start") and cleaned["start"] > fmt.per_sheet:
            self.add_error(
                "start", _("Dieser Bogen hat nur %(n)d Etiketten.") % {"n": fmt.per_sheet}
            )
        return cleaned

    def copies(self):
        data = self.cleaned_data
        copies = Copy.objects.select_related("title").order_by("inventory_number")
        choice = data["auswahl"]
        if choice == "neu":
            return copies.filter(label_printed_at__isnull=True)
        if choice == "kategorie":
            return copies.filter(title__category=data["kategorie"])
        if choice == "standort":
            return copies.filter(location=data["standort"])
        if choice == "titel":
            return copies.filter(title=data["titel"])
        if choice == "exemplar":
            return copies.filter(pk__in=[c.pk for c in data["exemplar"]])
        return copies


def _pdf_response(content, filename):
    response = HttpResponse(content, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response


@require("can_manage_catalog")
def labels_page(request):
    data = request.POST if request.method == "POST" else (request.GET or None)
    initial = {"auswahl": "neu", "format": labels.DEFAULT_FORMAT, "start": 1}
    if data is not None and "format" not in data:
        data = {**initial, **data.dict(), "exemplar": data.getlist("exemplar")}
    form = LabelForm(data, initial=initial)
    settings_row = SchoolSettings.current()
    copies = None
    if form.is_bound and form.is_valid():
        copies = list(form.copies())
        fmt = labels.FORMATS[form.cleaned_data["format"]]
        action = request.POST.get("action")
        if action == "pdf" and copies:
            pdf = labels.labels_pdf(
                copies,
                fmt,
                form.cleaned_data["start"],
                settings_row.label_offset_x,
                settings_row.label_offset_y,
            )
            return _pdf_response(pdf, f"etiketten-{fmt.code}.pdf")
        if action == "test":
            pdf = labels.test_page_pdf(
                fmt, settings_row.label_offset_x, settings_row.label_offset_y
            )
            return _pdf_response(pdf, f"testseite-{fmt.code}.pdf")
        if action == "mark" and copies:
            Copy.objects.filter(pk__in=[c.pk for c in copies]).update(
                label_printed_at=timezone.now()
            )
            messages.success(
                request, _("%(n)d Etiketten als gedruckt markiert.") % {"n": len(copies)}
            )
            return redirect("labels")
    return render(
        request,
        "catalog/labels.html",
        {"form": form, "copies": copies, "settings_row": settings_row},
    )


@require("can_manage_catalog")
def poster(request):
    from django.conf import settings

    school = School.objects.filter(pk=default_school_id()).first()
    name = school.name if school and school.name != "Meine Schule" else ""  # Platzhalter
    return _pdf_response(labels.poster_pdf(settings.SITE_URL, name), "fundus-plakat.pdf")
