from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from fundus.accounts.models import User
from fundus.accounts.permissions import require
from fundus.catalog.models import Copy, Title
from fundus.catalog.text import normalize
from fundus.loans import requests, services
from fundus.loans.forms import LendForm, RequestForm, contents_check
from fundus.loans.models import Loan


def home(request):
    loans = (
        Loan.objects.filter(borrower=request.user, status=Loan.Status.LENT)
        .select_related("copy__title")
        .order_by("due_date")
    )
    my_requests = (
        Loan.objects.filter(borrower=request.user, status__in=Loan.OPEN_REQUEST)
        .select_related("title__team", "approved_by")
        .order_by("requested_at")
    )
    return render(
        request,
        "loans/home.html",
        {
            "loans": loans,
            "my_requests": my_requests,
            "team_requests": requests_context(request.user),
            "today": timezone.localdate(),
        },
    )


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
    if title.approval_required:
        context["own_request"] = requests.open_request(title, user)
        if context["can_lend_for_others"] and loan is None:
            context["handover_requests"] = requests_context(user, title)
    if loan is None:
        blocked = title.approval_required and not services.can_lend_for_others(user, title)
        context["lend_blocked"] = blocked
        if blocked and not context.get("own_request"):
            context["request_form"] = RequestForm()
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
            "without_team": Title.objects.filter(approval_required=True, team__isnull=True),
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


def _safe_local_path(value, default):
    return value if value.startswith("/") and not value.startswith("//") else default


def scanner(request):
    """Kamera-Scanner. ?ziel=isbn&zurueck=/pfad/ liefert eine ISBN an ein Formular zurück."""
    mode = request.GET.get("ziel") if request.GET.get("ziel") in ("isbn", "kiste") else "exemplar"
    if mode == "kiste":
        back = reverse("return_box")
        target = f"{back}?nummer=__CODE__"
    elif mode == "isbn":
        back = _safe_local_path(request.GET.get("zurueck", ""), reverse("title_create"))
        target = f"{back}{'&' if '?' in back else '?'}isbn=__CODE__"
    else:
        back = reverse("home")
        target = reverse("scan", args=["__CODE__"])
    return render(request, "loans/scanner.html", {"mode": mode, "target": target, "back": back})


BOX_SESSION_KEY = "return_box"


def _box_log(request, copy, text):
    log = request.session.get(BOX_SESSION_KEY, [])
    log.insert(0, {"number": copy.inventory_number, "title": copy.title.title, "text": text})
    request.session[BOX_SESSION_KEY] = log[:50]


@require("can_manage_catalog")
def return_box(request):
    """Rückgabekiste: viele Exemplare nacheinander zurückbuchen.

    Handscanner (Formular mit Enter) bucht sofort zurück; aus dem Kamera-Scanner
    kommt die Nummer per GET und wird mit einem Tipp bestätigt. Bei Testkoffern
    wird zuerst die Inhaltsliste abgefragt.
    """
    number = (request.POST.get("nummer") or request.GET.get("nummer") or "").strip()
    copy = None
    check = None
    if number:
        copy = Copy.objects.filter(inventory_number__iexact=number).select_related("title").first()
        if copy is None:
            messages.error(request, _("Keine Inventarnummer „%(n)s“ gefunden.") % {"n": number})
        elif not copy.loans.filter(status=Loan.Status.LENT).exists():
            messages.warning(
                request, _("%(n)s ist nicht ausgeliehen.") % {"n": copy.inventory_number}
            )
            copy = None
        elif copy.title.contents_items:
            check = copy  # erst Inhalt prüfen
        elif request.method == "POST":
            services.return_copy(copy, by=request.user)
            _box_log(request, copy, _("zurück"))
            messages.success(request, _("%(n)s zurückgebucht.") % {"n": copy.inventory_number})
            return redirect("return_box")
    if request.method == "POST" and "pruefung" in request.POST and check:
        complete, missing = contents_check(check.title, request.POST)
        services.return_copy(check, by=request.user, complete=complete, missing=missing)
        _box_log(
            request,
            check,
            _("zurück, vollständig")
            if complete
            else _("zurück, fehlt: %(m)s") % {"m": ", ".join(missing)},
        )
        messages.success(request, _("%(n)s zurückgebucht.") % {"n": check.inventory_number})
        return redirect("return_box")
    return render(
        request,
        "loans/return_box.html",
        {
            "confirm": copy if (copy and not check and request.method == "GET") else None,
            "check": check,
            "log": request.session.get(BOX_SESSION_KEY, []),
        },
    )


# Anfragen für freigabepflichtige Titel


def requests_context(user, title=None):
    """Offene Anfragen, über die `user` entscheiden darf (optional nur ein Titel)."""
    loans = Loan.objects.filter(status__in=Loan.OPEN_REQUEST).select_related(
        "title__team", "borrower", "approved_by"
    )
    if title is not None:
        loans = loans.filter(title=title)
    elif not user.can_manage_catalog:
        loans = loans.filter(title__team__members=user)
    return [
        loan
        for loan in loans.order_by("requested_at")
        if services.can_lend_for_others(user, loan.title)
    ]


@require_POST
def request_create(request, pk):
    title = get_object_or_404(Title, pk=pk)
    form = RequestForm(request.POST)
    if form.is_valid():
        try:
            requests.request_title(title, by=request.user, **form.cleaned_data)
        except services.LoanError as error:
            messages.error(request, str(error))
        else:
            messages.success(
                request,
                _("Angefragt. %(team)s bekommt Bescheid; Sie werden per E-Mail informiert.")
                % {"team": services.contact_for(title)},
            )
    else:
        for errors in form.errors.values():
            messages.error(request, " ".join(errors))
    return redirect(request.POST.get("weiter") or reverse("title_detail", args=[pk]))


def _request_action(request, pk, action, success):
    loan = get_object_or_404(Loan, pk=pk)
    try:
        action(loan)
    except services.LoanError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, success)
    return redirect(request.POST.get("weiter") or "home")


@require_POST
def request_approve(request, pk):
    return _request_action(
        request,
        pk,
        lambda loan: requests.approve(loan, by=request.user),
        _("Genehmigt. Die Lehrkraft wird informiert und holt das Material ab."),
    )


@require_POST
def request_reject(request, pk):
    return _request_action(
        request,
        pk,
        lambda loan: requests.reject(loan, by=request.user, reason=request.POST.get("grund", "")),
        _("Abgelehnt. Die Lehrkraft wird informiert."),
    )


@require_POST
def request_withdraw(request, pk):
    return _request_action(
        request,
        pk,
        lambda loan: requests.withdraw(loan, by=request.user),
        _("Anfrage zurückgezogen."),
    )


@require_POST
def hand_over(request, pk, copy_pk):
    loan = get_object_or_404(Loan, pk=pk)
    copy = get_object_or_404(Copy, pk=copy_pk)
    try:
        loan = requests.hand_over(loan, copy, by=request.user)
    except services.LoanError as error:
        messages.error(request, str(error))
    else:
        messages.success(
            request,
            _("%(n)s an %(p)s übergeben, bis %(d)s.")
            % {
                "n": copy.inventory_number,
                "p": loan.borrower,
                "d": loan.due_date.strftime("%d.%m.%Y"),
            },
        )
    return redirect("copy_detail", pk=copy.pk)
