from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import ProtectedError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from fundus.accounts.permissions import require
from fundus.catalog.forms import (
    CategoryForm,
    CopiesAddForm,
    CopyForm,
    LocationForm,
    SupportFocusForm,
    TitleForm,
)
from fundus.catalog.history import history_entries
from fundus.catalog.models import Category, Copy, Location, SupportFocus, Title
from fundus.catalog.search import exact_copy, outdated_before_year, search_titles

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
        Title.objects.select_related("category", "responsible", "deputy").prefetch_related(
            "support_focuses"
        ),
        pk=pk,
    )
    copies = (
        Copy.objects.filter(title=title)
        .select_related("location")
        .with_availability()
        .order_by("inventory_number")
    )
    return render(request, "catalog/title_detail.html", {"title": title, "copies": copies})


@require("can_manage_catalog")
def title_create(request):
    form = TitleForm(request.POST or None, request.FILES or None)
    copies_form = CopiesAddForm(request.POST or None, prefix="copies", required=False)
    if request.method == "POST" and form.is_valid() and copies_form.is_valid():
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
        {"form": form, "copies_form": copies_form, "is_new": True},
    )


@require("can_manage_catalog")
def title_edit(request, pk):
    title = get_object_or_404(Title, pk=pk)
    form = TitleForm(request.POST or None, request.FILES or None, instance=title)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Änderungen gespeichert."))
        return redirect("title_detail", pk=title.pk)
    return render(request, "catalog/title_form.html", {"form": form, "title": title})


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
    loans = copy.loans.select_related("borrower")[:20] if request.user.can_manage_catalog else []
    return render(request, "catalog/copy_detail.html", {"copy": copy, "loans": loans})


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
}


def _history_model(kind):
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
