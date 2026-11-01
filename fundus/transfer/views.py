import json
import uuid

from django import forms
from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_POST

from fundus.accounts.permissions import require
from fundus.catalog.models import Category
from fundus.transfer import importer
from fundus.transfer.models import ImportTemplate

SESSION_KEY = "catalog_import"
MAX_UPLOAD = 10 * 1024 * 1024


class UploadForm(forms.Form):
    file = forms.FileField(
        label=gettext_lazy("Datei"),
        help_text=gettext_lazy("CSV oder Excel (.xlsx), erste Zeile mit Spaltennamen."),
        widget=forms.ClearableFileInput(attrs={"accept": ".csv,.txt,.xlsx"}),
    )

    def clean_file(self):
        upload = self.cleaned_data["file"]
        if upload.size > MAX_UPLOAD:
            raise forms.ValidationError(_("Die Datei ist zu groß (höchstens 10 MB)."))
        return upload


def _import_dir():
    path = settings.DATA_DIR / "imports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _load(request):
    state = request.session.get(SESSION_KEY)
    if not state or "token" not in state:
        return None, None
    path = _import_dir() / f"{state['token']}.json"
    if not path.exists():
        return None, None
    return state, json.loads(path.read_text(encoding="utf-8"))


def _options(state):
    category = None
    if state.get("default_category"):
        category = Category.objects.filter(pk=state["default_category"]).first()
    return importer.Options(
        default_category=category,
        create_missing=state.get("create_missing", True),
        lendable_default=state.get("lendable_default", False),
    )


@require("is_admin")
def upload(request):
    form = UploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        file = form.cleaned_data["file"]
        try:
            header, rows = importer.read_table(file.name, file.read())
        except importer.ImportFileError as error:
            form.add_error("file", str(error))
        else:
            token = uuid.uuid4().hex
            (_import_dir() / f"{token}.json").write_text(
                json.dumps({"header": header, "rows": rows}), encoding="utf-8"
            )
            request.session[SESSION_KEY] = {
                "token": token,
                "filename": file.name,
                "mapping": importer.guess_mapping(header),
            }
            return redirect("import_mapping")
    return render(request, "transfer/import_upload.html", {"form": form})


@require("is_admin")
def mapping(request):
    state, table = _load(request)
    if not state:
        return redirect("import_upload")
    header, rows = table["header"], table["rows"]
    templates = ImportTemplate.objects.all()

    if request.method == "POST":
        if request.POST.get("apply_template"):
            template = templates.filter(pk=request.POST["apply_template"]).first()
            if template:
                by_name = {name: i for i, name in enumerate(header)}
                state["mapping"] = {
                    f: by_name[col] for f, col in template.mapping.items() if col in by_name
                }
                request.session[SESSION_KEY] = state
                messages.success(request, _("Vorlage „%(t)s“ angewendet.") % {"t": template})
            return redirect("import_mapping")

        new_mapping = {}
        for target in importer.FIELDS:
            value = request.POST.get(f"map_{target}", "")
            if value.isdigit() and int(value) < len(header):
                new_mapping[target] = int(value)
        state.update(
            mapping=new_mapping,
            default_category=request.POST.get("default_category") or None,
            create_missing=bool(request.POST.get("create_missing")),
            lendable_default=bool(request.POST.get("lendable_default")),
        )
        request.session[SESSION_KEY] = state

        missing = [importer.FIELDS[f] for f in importer.REQUIRED if f not in new_mapping]
        if missing:
            messages.error(
                request,
                _("Bitte Spalten zuordnen für: %(f)s") % {"f": ", ".join(map(str, missing))},
            )
            return redirect("import_mapping")

        template_name = request.POST.get("save_template", "").strip()
        if template_name:
            ImportTemplate.objects.update_or_create(
                name=template_name,
                defaults={"mapping": {f: header[i] for f, i in new_mapping.items()}},
            )
        return redirect("import_preview")

    samples = rows[:3]
    columns = [
        {"index": i, "name": name, "samples": [r[i] for r in samples if r[i]]}
        for i, name in enumerate(header)
    ]
    targets = [
        {
            "key": key,
            "label": label,
            "required": key in importer.REQUIRED,
            "selected": state["mapping"].get(key),
        }
        for key, label in importer.FIELDS.items()
    ]
    return render(
        request,
        "transfer/import_mapping.html",
        {
            "state": state,
            "columns": columns,
            "targets": targets,
            "row_count": len(rows),
            "categories": Category.objects.all(),
            "templates": templates,
        },
    )


@require("is_admin")
def preview(request):
    state, table = _load(request)
    if not state:
        return redirect("import_upload")
    results = importer.analyze(table["rows"], state["mapping"], _options(state))
    return render(
        request,
        "transfer/import_preview.html",
        {
            "state": state,
            "results": results,
            "summary": importer.summarize(results),
            "fields": importer.FIELDS,
        },
    )


@require("is_admin")
@require_POST
def confirm(request):
    state, table = _load(request)
    if not state:
        messages.warning(request, _("Kein Import vorbereitet. Bitte die Datei neu hochladen."))
        return redirect("import_upload")
    options = _options(state)
    results = importer.analyze(table["rows"], state["mapping"], options)
    counts = importer.run_import(results, options)

    report = importer.report_csv(results)
    (_import_dir() / f"{state['token']}.json").unlink(missing_ok=True)
    (_import_dir() / f"{state['token']}-bericht.csv").write_text(report, encoding="utf-8")
    request.session[SESSION_KEY] = {"report": state["token"]}
    messages.success(
        request,
        _("Import abgeschlossen: %(c)d Exemplare zu %(t)d Titeln.")
        % {"c": counts["copies"], "t": counts["titles"]},
    )
    return render(
        request,
        "transfer/import_done.html",
        {"counts": counts, "summary": importer.summarize(results)},
    )


@require("is_admin")
def report(request):
    state = request.session.get(SESSION_KEY) or {}
    path = _import_dir() / f"{state.get('report', '')}-bericht.csv"
    if not state.get("report") or not path.exists():
        return redirect("import_upload")
    response = HttpResponse(path.read_text(encoding="utf-8"), content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="importbericht.csv"'
    return response
