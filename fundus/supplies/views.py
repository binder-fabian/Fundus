from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from fundus.accounts.permissions import require
from fundus.catalog.labels import reorder_cards_pdf
from fundus.supplies import services
from fundus.supplies.forms import CardsForm, ConsumableForm, QuantityForm
from fundus.supplies.models import Consumable, ReorderNotice


def consumable_list(request):
    items = Consumable.objects.select_related("title", "location").prefetch_related("notices")
    query = request.GET.get("q", "").strip()
    if query:
        items = items.filter(name__icontains=query) | items.filter(code__iexact=query)
    return render(request, "supplies/list.html", {"items": items, "query": query})


def consumable_detail(request, pk):
    item = get_object_or_404(Consumable.objects.select_related("title", "location"), pk=pk)
    return render(
        request,
        "supplies/detail.html",
        {
            "item": item,
            "notice": item.open_notice(),
            "quantity_form": QuantityForm(),
            "history": item.notices.select_related("created_by", "handled_by")[:10],
        },
    )


@require("can_manage_catalog")
def consumable_edit(request, pk=None):
    item = get_object_or_404(Consumable, pk=pk) if pk else None
    initial = {} if item else {"code": services.next_code(), "title": request.GET.get("titel")}
    form = ConsumableForm(request.POST or None, instance=item, initial=initial)
    if request.method == "POST":
        if "delete" in request.POST and item:
            item.delete()
            messages.success(request, _("„%(n)s“ gelöscht.") % {"n": item})
            return redirect("consumable_list")
        if form.is_valid():
            item = form.save()
            messages.success(request, _("Gespeichert."))
            return redirect("consumable_detail", pk=item.pk)
    return render(request, "supplies/form.html", {"form": form, "item": item})


@require_POST
def reorder(request, pk):
    item = get_object_or_404(Consumable, pk=pk)
    _notice, created = services.request_reorder(item, by=request.user)
    if created:
        messages.success(request, _("Danke! Das Sekretariat bestellt „%(n)s“ nach.") % {"n": item})
    else:
        messages.info(request, _("„%(n)s“ ist schon zur Nachbestellung gemeldet.") % {"n": item})
    return redirect("consumable_detail", pk=pk)


def _quantity_action(request, pk, action, text):
    item = get_object_or_404(Consumable, pk=pk)
    form = QuantityForm(request.POST)
    if not form.is_valid():
        messages.error(request, _("Bitte eine gültige Menge angeben."))
        return redirect("consumable_detail", pk=pk)
    try:
        result = action(item, request.user, form.cleaned_data["quantity"])
    except services.SupplyError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, text(result))
    return redirect("consumable_detail", pk=pk)


@require_POST
def take(request, pk):
    def text(result):
        item, notice = result
        message = _("Entnahme gebucht, Bestand jetzt %(s)d.") % {"s": item.stock}
        if notice:
            message += " " + _("Mindestmenge erreicht – das Sekretariat ist informiert.")
        return message

    return _quantity_action(request, pk, services.take, text)


@require("can_manage_catalog")
@require_POST
def restock(request, pk):
    return _quantity_action(
        request,
        pk,
        services.restock,
        lambda item: _("Aufgefüllt, Bestand jetzt %(s)d.") % {"s": item.stock},
    )


@require("can_handle_orders")
def reorder_list(request):
    show_done = request.GET.get("erledigt") == "1"
    notices = ReorderNotice.objects.select_related("consumable", "created_by", "handled_by")
    notices = (
        notices.exclude(status__in=ReorderNotice.OPEN)
        if show_done
        else notices.filter(status__in=ReorderNotice.OPEN)
    )
    return render(
        request,
        "supplies/reorders.html",
        {"notices": notices[:200], "show_done": show_done, "quantity_form": QuantityForm()},
    )


@require("can_handle_orders")
@require_POST
def notice_action(request, pk, action):
    notice = get_object_or_404(ReorderNotice, pk=pk)
    try:
        if action == "bestellt":
            services.mark_ordered(notice, request.user)
            messages.success(request, _("Als bestellt markiert."))
        elif action == "geliefert":
            form = QuantityForm(request.POST)
            quantity = form.cleaned_data["quantity"] if form.is_valid() else None
            services.mark_delivered(notice, request.user, quantity)
            messages.success(request, _("Als geliefert markiert."))
        elif action == "verwerfen":
            services.cancel(notice, request.user)
            messages.success(request, _("Hinweis verworfen."))
    except services.SupplyError as error:
        messages.error(request, str(error))
    return redirect("reorder_list")


@require("can_manage_catalog")
def cards(request):
    form = CardsForm(request.POST or None, initial={"items": request.GET.getlist("material")})
    if request.method == "POST" and form.is_valid():
        response = HttpResponse(
            reorder_cards_pdf(list(form.cleaned_data["items"])), content_type="application/pdf"
        )
        response["Content-Disposition"] = 'inline; filename="nachbestellkarten.pdf"'
        return response
    return render(request, "supplies/cards.html", {"form": form})
