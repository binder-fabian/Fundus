from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from fundus.accounts.models import User
from fundus.accounts.permissions import require
from fundus.catalog.models import Copy
from fundus.catalog.text import normalize
from fundus.loans import services
from fundus.loans.forms import LendForm, contents_check
from fundus.loans.models import Loan


def home(request):
    loans = (
        Loan.objects.filter(borrower=request.user, status=Loan.Status.LENT)
        .select_related("copy__title")
        .order_by("due_date")
    )
    return render(request, "loans/home.html", {"loans": loans, "today": timezone.localdate()})


def scan(request, number=None):
    """Ziel eines Scans: öffnet das Exemplar zur Inventarnummer."""
    number = (number or request.GET.get("nummer", "")).strip()
    copy = Copy.objects.filter(inventory_number__iexact=number).first() if number else None
    if copy:
        return redirect("copy_detail", pk=copy.pk)
    if number:
        messages.error(request, _("Keine Inventarnummer „%(n)s“ gefunden.") % {"n": number})
    return redirect(request.GET.get("zurueck") or "home")


def copy_actions(request, copy):
    """Kontext für die Aktionen auf der Exemplarseite."""
    user = request.user
    title = copy.title
    loan = copy.loans.filter(status=Loan.Status.LENT).select_related("borrower").first()
    context = {
        "loan": loan,
        "show_borrower": loan is not None and services.can_see_borrower(user, title),
        "can_lend_for_others": services.can_lend_for_others(user, title),
    }
    if not title.lendable:
        return context
    if loan is None:
        blocked = title.approval_required and not services.can_lend_for_others(user, title)
        context["lend_blocked"] = blocked
        if not blocked:
            context["lend_form"] = LendForm(
                initial={"due_date": services.default_due_date(copy), "borrower": user.pk},
                for_others=context["can_lend_for_others"],
            )
    else:
        context["can_return"] = services.can_return(user, loan)
        context["can_extend"] = (
            loan.borrower_id == user.pk or user.can_manage_catalog
        ) and not services.pending_request(copy)
    return context


@require_POST
def lend(request, pk):
    copy = get_object_or_404(Copy.objects.select_related("title"), pk=pk)
    for_others = services.can_lend_for_others(request.user, copy.title)
    form = LendForm(request.POST, for_others=for_others)
    if not form.is_valid():
        for errors in form.errors.values():
            messages.error(request, " ".join(errors))
        return redirect("copy_detail", pk=pk)
    borrower = form.cleaned_data.get("borrower") or request.user
    try:
        loan = services.lend(
            copy, by=request.user, borrower=borrower, due_date=form.cleaned_data["due_date"]
        )
    except services.LoanError as error:
        messages.error(request, str(error))
    else:
        who = "" if borrower == request.user else _(" für %(p)s") % {"p": borrower}
        messages.success(
            request,
            _("Ausgeliehen%(who)s bis %(d)s.")
            % {"who": who, "d": loan.due_date.strftime("%d.%m.%Y")},
        )
    return redirect("copy_detail", pk=pk)


@require_POST
def give_back(request, pk):
    copy = get_object_or_404(Copy.objects.select_related("title"), pk=pk)
    complete, missing = contents_check(copy.title, request.POST)
    try:
        services.return_copy(copy, by=request.user, complete=complete, missing=missing)
    except services.LoanError as error:
        messages.error(request, str(error))
    else:
        text = _("Zurückgegeben.")
        if complete is False:
            text += " " + _("Als unvollständig markiert: %(m)s") % {"m": ", ".join(missing)}
        messages.success(request, text)
    if request.POST.get("weiter"):
        return redirect(request.POST["weiter"])
    return redirect("copy_detail", pk=pk)


@require_POST
def extend(request, pk):
    loan = get_object_or_404(Loan, pk=pk)
    try:
        loan = services.extend(loan, by=request.user)
    except services.LoanError as error:
        messages.error(request, str(error))
    else:
        messages.success(
            request, _("Verlängert bis %(d)s.") % {"d": loan.due_date.strftime("%d.%m.%Y")}
        )
    return redirect(request.POST.get("weiter") or "home")


@require("can_manage_catalog")
def overview(request):
    view = request.GET.get("ansicht", "offen")
    today = timezone.localdate()
    loans = Loan.objects.select_related("copy__title", "borrower").order_by("due_date")
    if view == "ueberfaellig":
        loans = loans.filter(status=Loan.Status.LENT, due_date__lt=today)
    elif view == "alle":
        loans = loans.exclude(status__in=[Loan.Status.REQUESTED, Loan.Status.REJECTED]).order_by(
            "-lent_at"
        )
    else:
        view = "offen"
        loans = loans.filter(status=Loan.Status.LENT)

    teacher = None
    if request.GET.get("lehrkraft"):
        teacher = User.objects.filter(pk=request.GET["lehrkraft"]).first()
        if teacher:
            loans = loans.filter(borrower=teacher)
    query = request.GET.get("q", "").strip()
    if query:
        loans = loans.filter(
            Q(copy__inventory_number__icontains=query)
            | Q(copy__title__search_text__contains=normalize(query))
        )
    page = Paginator(loans, 50).get_page(request.GET.get("seite"))
    params = request.GET.copy()
    params.pop("seite", None)
    return render(
        request,
        "loans/overview.html",
        {
            "page": page,
            "view": view,
            "teacher": teacher,
            "teachers": User.objects.filter(loans__status=Loan.Status.LENT).distinct(),
            "incomplete": Copy.objects.filter(incomplete=True).select_related("title"),
            "today": today,
            "query_string": params.urlencode(),
            "counts": {
                "offen": Loan.objects.filter(status=Loan.Status.LENT).count(),
                "ueberfaellig": Loan.objects.filter(
                    status=Loan.Status.LENT, due_date__lt=today
                ).count(),
            },
        },
    )
