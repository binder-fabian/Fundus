import contextlib
import io

from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import ProtectedError
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from fundus.accounts.permissions import require
from fundus.catalog import bulk, isbn_lookup
from fundus.catalog.forms import (
    CategoryForm,
    CopiesAddForm,
    CopyForm,
    LocationForm,
    SupportFocusForm,
    TeamForm,
    TitleForm,
    shrink_cover,
)
from fundus.catalog.history import history_entries
from fundus.catalog.isbn import validate_isbn
from fundus.catalog.models import Category, Copy, Location, SupportFocus, Team, Title
from fundus.catalog.search import exact_copy, outdated_before_year, search_titles
from fundus.core.models import SchoolSettings

PAGE_SIZE = 50


def title_list(request):
    query = request.GET.get("q", "")
    # Exakte Inventarnummer (z. B. per USB-Handscanner mit Enter) öffnet das Exemplar.
    if query and not request.htmx:
        copy = exact_copy(query)
        if copy:
            return redirect("copy_detail", pk=copy.pk)

    form, titles = search_titles(request.GET)
    page = Paginator(titles, PAGE_SIZE).get_page(request.GET.get("seite"))
    params = request.GET.copy()
    params.pop("seite", None)
    context = {
        "form": form,
        "page": page,
        "query_string": params.urlencode(),
        "exact": exact_copy(query) if request.htmx else None,
        "outdated_before": outdated_before_year(),
        "filtered": any(v for k, v in request.GET.items() if k != "seite"),
    }
    template = "catalog/_title_results.html" if request.htmx else "catalog/title_list.html"
    return render(request, template, context)


def title_detail(request, pk):
    title = get_object_or_404(
        Title.objects.select_related("category", "team").prefetch_related("support_focuses"),
        pk=pk,
    )
    copies = (
        Copy.objects.filter(title=title)
        .select_related("location")
        .with_availability()
        .order_by("inventory_number")
    )
    if title.lendable:
        from fundus.loans.services import can_see_borrower

        copies = list(copies)
        if can_see_borrower(request.user, title):
            open_loans = title.loans.filter(status="lent").select_related("borrower")
            names = {loan.copy_id: loan.borrower_display for loan in open_loans}
            for c in copies:
                c.borrower_name = names.get(c.pk, "")
    context = {"title": title, "copies": copies}
    if title.approval_required and title.lendable:
        from fundus.loans import requests as loan_requests
        from fundus.loans.forms import RequestForm
        from fundus.loans.services import can_lend_for_others

        context["own_request"] = loan_requests.open_request(title, request.user)
        if not context["own_request"] and not can_lend_for_others(request.user, title):
            context["request_form"] = RequestForm()
    return render(request, "catalog/title_detail.html", context)


def _isbn_lookup_into(request, form_class, instance=None, source=None):
    """Ruft Daten zur eingegebenen ISBN ab und zeigt das Formular vorausgefüllt
    wieder an. Gespeichert wird erst, wenn die Person bestätigt."""
    source = request.POST if source is None else source
    data = {k: v for k, v in source.items() if k != "csrfmiddlewaretoken"}
    data["support_focuses"] = source.getlist("support_focuses")
    isbn = source.get("isbn", "")
    probe = form_class(instance=instance)
    try:
        validate_isbn(isbn)
    except ValidationError:
        messages.error(request, _("Bitte zuerst eine gültige ISBN eingeben."))
        return form_class(initial=data, instance=instance)

    result = isbn_lookup.lookup(isbn)
    filled = probe.initial_from_lookup(data, result)
    if result.found:
        text = _("Daten von %(src)s übernommen. Bitte prüfen und speichern.") % {
            "src": ", ".join(result.sources)
        }
        if not filled:
            text = _("Gefunden bei %(src)s; alle Felder waren schon ausgefüllt.") % {
                "src": ", ".join(result.sources)
            }
        if result.cover_url:
            text += " " + _("Ein Cover wird beim Speichern übernommen.")
        messages.success(request, text)
    elif result.failed and not result.sources:
        messages.warning(
            request, _("Abruf gerade nicht möglich (keine Verbindung?). Bitte von Hand ausfüllen.")
        )
    else:
        messages.warning(request, _("Zu dieser ISBN wurden keine Daten gefunden."))
    return form_class(initial=data, instance=instance)


def _lookup_enabled():
    return SchoolSettings.current().isbn_lookup_enabled


@require("can_manage_catalog")
def title_create(request):
    lookup = request.method == "POST" and "lookup" in request.POST and _lookup_enabled()
    if lookup:
        form = _isbn_lookup_into(request, TitleForm)
        copies_form = CopiesAddForm(
            initial={k[7:]: v for k, v in request.POST.items() if k.startswith("copies-")},
            prefix="copies",
            required=False,
        )
    elif request.method == "GET" and request.GET.get("isbn"):
        # Aus dem Kamera-Scanner: ISBN übernehmen und gleich abrufen.
        if _lookup_enabled():
            form = _isbn_lookup_into(request, TitleForm, source=request.GET)
        else:
            form = TitleForm(initial={"isbn": request.GET["isbn"]})
        copies_form = CopiesAddForm(prefix="copies", required=False)
    else:
        form = TitleForm(request.POST or None, request.FILES or None)
        copies_form = CopiesAddForm(request.POST or None, prefix="copies", required=False)
    if request.method == "POST" and not lookup and form.is_valid() and copies_form.is_valid():
        with transaction.atomic():
            title = form.save()
            created = copies_form.save(title)
        messages.success(
            request,
            _("„%(title)s“ angelegt, %(n)d Exemplare.") % {"title": title, "n": len(created)},
        )
        return redirect("title_detail", pk=title.pk)
    return render(
        request,
        "catalog/title_form.html",
        {
            "form": form,
            "copies_form": copies_form,
            "is_new": True,
            "isbn_lookup": _lookup_enabled(),
        },
    )


@require("can_manage_catalog")
def title_edit(request, pk):
    title = get_object_or_404(Title, pk=pk)
    lookup = request.method == "POST" and "lookup" in request.POST and _lookup_enabled()
    if lookup:
        form = _isbn_lookup_into(request, TitleForm, instance=title)
    else:
        form = TitleForm(request.POST or None, request.FILES or None, instance=title)
    if request.method == "POST" and not lookup and form.is_valid():
        form.save()
        messages.success(request, _("Änderungen gespeichert."))
        return redirect("title_detail", pk=title.pk)
    return render(
        request,
        "catalog/title_form.html",
        {"form": form, "title": title, "isbn_lookup": _lookup_enabled()},
    )


@require("can_manage_catalog")
def title_delete(request, pk):
    title = get_object_or_404(Title, pk=pk)
    if title.copies.exists():
        messages.error(request, _("Titel mit Exemplaren können nicht gelöscht werden."))
        return redirect("title_detail", pk=pk)
    if request.method == "POST":
        title.delete()
        messages.success(request, _("„%(title)s“ gelöscht.") % {"title": title})
        return redirect("title_list")
    return render(request, "catalog/confirm_delete.html", {"object": title, "cancel": title})


@require("can_manage_catalog")
def copies_add(request, pk):
    title = get_object_or_404(Title, pk=pk)
    form = CopiesAddForm(request.POST or None, title=title)
    if request.method == "POST" and form.is_valid():
        created = form.save(title)
        messages.success(request, _("%(n)d Exemplare angelegt.") % {"n": len(created)})
        return redirect("title_detail", pk=pk)
    return render(request, "catalog/copies_add.html", {"form": form, "title": title})


def copy_detail(request, pk):
    copy = get_object_or_404(
        Copy.objects.select_related("title__category", "location").with_availability(), pk=pk
    )
    from fundus.loans.views import copy_actions

    loans = copy.loans.select_related("borrower")[:20] if request.user.can_manage_catalog else []
    return render(
        request,
        "catalog/copy_detail.html",
        {"copy": copy, "loans": loans, **copy_actions(request, copy)},
    )


@require("can_manage_catalog")
def copy_edit(request, pk):
    copy = get_object_or_404(Copy.objects.select_related("title"), pk=pk)
    form = CopyForm(request.POST or None, instance=copy)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Änderungen gespeichert."))
        return redirect("copy_detail", pk=pk)
    return render(request, "catalog/copy_form.html", {"form": form, "copy": copy})


@require("can_manage_catalog")
def copy_delete(request, pk):
    copy = get_object_or_404(Copy.objects.select_related("title"), pk=pk)
    if copy.loans.exists():
        messages.error(
            request,
            _("Exemplare mit Ausleihen können nicht gelöscht werden. Als „beschädigt“ markieren?"),
        )
        return redirect("copy_detail", pk=pk)
    if request.method == "POST":
        title = copy.title
        copy.delete()
        messages.success(request, _("Exemplar %(n)s gelöscht.") % {"n": copy.inventory_number})
        return redirect("title_detail", pk=title.pk)
    return render(request, "catalog/confirm_delete.html", {"object": copy, "cancel": copy})


# Änderungsprotokoll

HISTORY_MODELS = {
    "titel": Title,
    "exemplar": Copy,
    "kategorie": Category,
    "foerderschwerpunkt": SupportFocus,
    "standort": Location,
    "team": Team,
}


def _history_model(kind):
    if kind == "material":
        from fundus.supplies.models import Consumable

        return Consumable
    try:
        return HISTORY_MODELS[kind]
    except KeyError:
        raise Http404 from None


@require("can_manage_catalog")
def history(request, kind, pk):
    model = _history_model(kind)
    records = model.history.filter(id=pk).select_related("history_user")
    if not records.exists():
        raise Http404
    current = model.objects.filter(pk=pk).first()
    return render(
        request,
        "catalog/history.html",
        {
            "kind": kind,
            "object": current,
            "label": str(current or records.first()),
            "entries": history_entries(records),
        },
    )


@require("can_manage_catalog")
@require_POST
def history_restore(request, kind, history_id):
    model = _history_model(kind)
    record = get_object_or_404(model.history, history_id=history_id)
    instance = record.instance
    instance._change_reason = _("Wiederhergestellt: Stand vom %(date)s") % {
        "date": record.history_date.strftime("%d.%m.%Y %H:%M")
    }
    try:
        instance.save()
    except Exception as error:  # z. B. inzwischen vergebene Inventarnummer
        messages.error(request, _("Wiederherstellen nicht möglich: %(e)s") % {"e": error})
    else:
        messages.success(request, _("Älterer Stand wiederhergestellt."))
    return redirect("history", kind=kind, pk=record.id)


# Stammdaten

MASTERDATA = {
    "kategorien": (Category, CategoryForm, _("Kategorien"), _("Kategorie"), "kategorie"),
    "foerderschwerpunkte": (
        SupportFocus,
        SupportFocusForm,
        _("Förderschwerpunkte"),
        _("Förderschwerpunkt"),
        "foerderschwerpunkt",
    ),
    "standorte": (Location, LocationForm, _("Standorte"), _("Standort"), "standort"),
    "teams": (Team, TeamForm, _("Teams"), _("Team"), "team"),
}


def _masterdata(kind):
    try:
        return MASTERDATA[kind]
    except KeyError:
        raise Http404 from None


@require("can_manage_catalog")
def masterdata_list(request, kind):
    model, _form, plural, singular, history_kind = _masterdata(kind)
    return render(
        request,
        "catalog/masterdata_list.html",
        {
            "kind": kind,
            "objects": model.objects.all(),
            "plural": plural,
            "singular": singular,
            "history_kind": history_kind,
            "kinds": {k: v[2] for k, v in MASTERDATA.items()},
        },
    )


@require("can_manage_catalog")
def masterdata_edit(request, kind, pk=None):
    model, form_class, plural, singular, _kind = _masterdata(kind)
    instance = get_object_or_404(model, pk=pk) if pk else None
    form = form_class(request.POST or None, instance=instance)
    if request.method == "POST":
        if "delete" in request.POST and instance:
            try:
                instance.delete()
            except ProtectedError:
                messages.error(
                    request,
                    _("„%(o)s“ wird noch verwendet und kann nicht gelöscht werden.")
                    % {"o": instance},
                )
                return redirect("masterdata_edit", kind=kind, pk=pk)
            messages.success(request, _("„%(o)s“ gelöscht.") % {"o": instance})
            return redirect("masterdata_list", kind=kind)
        if form.is_valid():
            form.save()
            messages.success(request, _("Gespeichert."))
            return redirect("masterdata_list", kind=kind)
    return render(
        request,
        "catalog/masterdata_form.html",
        {"form": form, "kind": kind, "singular": singular, "plural": plural, "object": instance},
    )


# Massenerfassung

BULK_SESSION_KEY = "bulk_isbns"


class BulkStartForm(forms.Form):
    isbns = forms.CharField(
        label=_("ISBNs"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 10, "autofocus": True, "autocomplete": "off"}),
        help_text=_("Mit dem Handscanner nacheinander scannen – jede ISBN landet in einer Zeile."),
    )
    file = forms.FileField(
        label=_("oder Datei mit ISBNs (CSV/TXT)"),
        required=False,
        widget=forms.ClearableFileInput(attrs={"accept": ".csv,.txt"}),
    )


class BulkCommonForm(forms.Form):
    category = forms.ModelChoiceField(Category.objects.all(), label=_("Kategorie für neue Titel"))
    location = forms.ModelChoiceField(
        Location.objects.all(), required=False, label=_("Standort der neuen Exemplare")
    )
    lendable = forms.BooleanField(required=False, label=_("neue Titel sind ausleihbar"))


@require("can_manage_catalog")
def bulk_start(request):
    form = BulkStartForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        text = form.cleaned_data["isbns"]
        upload = form.cleaned_data.get("file")
        if upload:
            raw = upload.read(1024 * 1024)
            text += "\n" + raw.decode("utf-8-sig", errors="replace")
        rows, invalid = bulk.parse_isbns(text)
        if invalid:
            messages.warning(
                request,
                _("Ungültig und ignoriert: %(list)s") % {"list": ", ".join(invalid[:20])},
            )
        if rows:
            request.session[BULK_SESSION_KEY] = rows
            return redirect("bulk_preview")
        form.add_error("isbns", _("Keine gültige ISBN gefunden."))
    return render(request, "catalog/bulk_start.html", {"form": form})


@require("can_manage_catalog")
def bulk_preview(request):
    rows = request.session.get(BULK_SESSION_KEY)
    if not rows:
        return redirect("bulk_start")
    form = BulkCommonForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        chosen = []
        for isbn, count in rows:
            if request.POST.get(f"include_{isbn}"):
                with contextlib.suppress(ValueError):
                    count = max(1, min(50, int(request.POST.get(f"count_{isbn}", count))))
                chosen.append((isbn, count))
        if not chosen:
            messages.error(request, _("Bitte mindestens eine Zeile auswählen."))
        else:
            new_titles, extended, copies, missing = bulk.create(
                chosen,
                form.cleaned_data["category"],
                form.cleaned_data["location"],
                form.cleaned_data["lendable"],
            )
            del request.session[BULK_SESSION_KEY]
            return render(
                request,
                "catalog/bulk_done.html",
                {
                    "new_titles": new_titles,
                    "extended": extended,
                    "copies": copies,
                    "missing": missing,
                    "fetch_covers": SchoolSettings.current().isbn_lookup_enabled,
                },
            )
    return render(
        request,
        "catalog/bulk_preview.html",
        {
            "rows": rows,
            "form": form,
            "total": sum(c for _i, c in rows),
            "lookup_enabled": _lookup_enabled(),
        },
    )


@require("can_manage_catalog")
def bulk_row(request, isbn):
    """Eine Vorschauzeile; wird per htmx einzeln nachgeladen."""
    count = dict(request.session.get(BULK_SESSION_KEY) or []).get(isbn, 1)
    title = bulk.existing_title(isbn)
    result = None
    if not title and _lookup_enabled():
        result = isbn_lookup.lookup(isbn)
    return render(
        request,
        "catalog/_bulk_row.html",
        {"isbn": isbn, "count": count, "title": title, "result": result, "loaded": True},
    )


@require("can_manage_catalog")
@require_POST
def fetch_cover(request, pk):
    """Holt nach der Massenerfassung das Cover von Open Library (einzeln per htmx)."""
    title = get_object_or_404(Title, pk=pk)
    status = _("kein Cover")
    if not title.cover and title.isbn and _lookup_enabled():
        result = isbn_lookup.lookup(title.isbn)
        data = isbn_lookup.download_cover(result.cover_url) if result.cover_url else None
        if data:
            title.cover = shrink_cover(io.BytesIO(data))
            title._change_reason = "Cover von Open Library"
            title.save()
            status = _("Cover übernommen")
    elif title.cover:
        status = _("Cover vorhanden")
    return HttpResponse(status)
