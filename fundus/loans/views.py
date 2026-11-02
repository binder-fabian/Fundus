import datetime

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from fundus.accounts.models import User
from fundus.accounts.permissions import require
from fundus.catalog.models import Copy, Title
from fundus.catalog.text import normalize
from fundus.core.models import SchoolSettings
from fundus.loans import requests, reservations, services, stats
from fundus.loans.forms import (
    LendForm,
    RequestForm,
    ReserveDaysForm,
    ReserveLessonsForm,
    contents_check,
)
from fundus.loans.models import Loan
from fundus.supplies.models import Consumable, ReorderNotice


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
            "my_reservations": reservations.my_reservations(request.user),
            "open_reorders": ReorderNotice.objects.filter(status=ReorderNotice.Status.OPEN).count()
            if request.user.can_handle_orders
            else 0,
            "today": timezone.localdate(),
            "anonymous": services.anonymous_mode(),
        },
    )


def scan(request, number=None):
    """Ziel eines Scans: öffnet das Exemplar zur Inventarnummer."""
    number = (number or request.GET.get("nummer", "")).strip()
    copy = Copy.objects.filter(inventory_number__iexact=number).first() if number else None
    if copy:
        return redirect("copy_detail", pk=copy.pk)
    item = Consumable.objects.filter(code__iexact=number).first() if number else None
    if item:
        return redirect("consumable_detail", pk=item.pk)
    if number:
        messages.error(request, _("Keine Inventarnummer „%(n)s“ gefunden.") % {"n": number})
    return redirect(request.GET.get("zurueck") or "home")


SUGGESTION_LIMIT = 8


def scan_suggestions(request):
    """Vorschläge beim Tippen im Feld „Inventarnummer“: Exemplare und
    Verbrauchsmaterial, deren Nummer oder Titel die Eingabe enthält."""
    query = request.GET.get("nummer", "").strip()
    copies, items = [], []
    if len(query) >= 2:
        words = normalize(query).split()
        title_match = Q()
        for word in words:
            title_match &= Q(title__search_text__contains=word)
        copies = list(
            Copy.objects.filter(Q(inventory_number__icontains=query) | title_match)
            .select_related("title")
            .order_by("inventory_number")[:SUGGESTION_LIMIT]
        )
        item_match = Q(code__icontains=query) | Q(name__icontains=query)
        items = list(
            Consumable.objects.filter(item_match).order_by("code")[: SUGGESTION_LIMIT - len(copies)]
        )
    return render(request, "loans/_scan_suggestions.html", {"copies": copies, "items": items})


def copy_actions(request, copy):
    """Kontext für die Aktionen auf der Exemplarseite."""
    user = request.user
    title = copy.title
    loan = copy.loans.filter(status=Loan.Status.LENT).select_related("borrower").first()
    anonymous = services.anonymous_mode()
    context = {
        "loan": loan,
        "show_borrower": loan is not None
        and (not loan.borrower_id or services.can_see_borrower(user, title)),
        "can_lend_for_others": services.can_lend_for_others(user, title),
        "anonymous": anonymous,
        "label_suggestions": label_suggestions() if anonymous else [],
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
            due = services.default_due_date(copy)
            pickup = None
            if not title.approval_required and not anonymous:
                pickup = reservations.pickup_candidate(title, borrower=user)
            if pickup:
                due = reservations.last_day(pickup.reserved_until)
                context["pickup"] = pickup
            latest = reservations.latest_due_date(title, exclude=[pickup.pk] if pickup else [])
            if latest is not None and latest < due:
                context["reservation_note"] = reservations.conflict_message(
                    title, exclude=[pickup.pk] if pickup else []
                )
                if latest >= timezone.localdate():
                    due = latest
                elif not pickup:
                    context["reservation_blocked"] = True
            context["lend_form"] = LendForm(
                initial={"due_date": due, "borrower": user.pk},
                for_others=context["can_lend_for_others"],
                anonymous=context["anonymous"],
            )
    else:
        context["can_return"] = services.can_return(user, loan)
        context["can_extend"] = services.can_extend(user, loan) and not services.pending_request(
            copy
        )
    return context


def reservation_context(request, title, days_form=None, lessons_form=None):
    config = SchoolSettings.current()
    capacity = reservations.capacity(title)
    anonymous = services.anonymous_mode() and not title.approval_required
    kwargs = {"capacity": capacity, "anonymous": anonymous, "approval": title.approval_required}
    tomorrow = timezone.localdate() + datetime.timedelta(days=1)
    upcoming = (
        Loan.objects.filter(
            title=title,
            status__in=reservations.BLOCKING,
            reserved_until__gt=timezone.now(),
        )
        .select_related("borrower")
        .order_by("reserved_from", "pk")
    )
    today = timezone.localdate()
    try:
        shown = datetime.date.fromisoformat(request.GET.get("woche", ""))
    except ValueError:
        shown = today + datetime.timedelta(days=2) if today.weekday() >= 5 else today
    monday = reservations.week_start(shown)
    lessons_initial = {"day": tomorrow}
    try:
        lessons_initial["day"] = datetime.date.fromisoformat(request.GET.get("tag", ""))
        lessons_initial["first"] = lessons_initial["last"] = int(request.GET.get("stunde", ""))
    except ValueError:
        pass
    grid = reservations.week_grid(title, monday, config.lessons)
    see_names = services.can_see_borrower(request.user, title)
    entries = reservations.collapse(upcoming)
    for entry in entries:
        entry.show_name = see_names or not entry.borrower_id or entry.borrower_id == request.user.pk
        entry.can_cancel = entry.status == Loan.Status.RESERVED and reservations.can_cancel(
            request.user, entry
        )
        entry.can_withdraw = (
            entry.status in Loan.OPEN_REQUEST and entry.borrower_id == request.user.pk
        )
    return {
        "title": title,
        "capacity": capacity,
        "anonymous": anonymous,
        "label_suggestions": label_suggestions() if anonymous else [],
        "days_form": days_form
        or ReserveDaysForm(initial={"first": tomorrow, "last": tomorrow}, prefix="tage", **kwargs),
        "lessons_form": lessons_form
        or ReserveLessonsForm(
            initial=lessons_initial, prefix="stunden", lessons=config.lessons, **kwargs
        ),
        "entries": entries,
        "grid": grid,
        "week_end": grid["days"][-1]["day"] if grid["days"] else monday,
        "monday": monday,
        "previous_week": monday - datetime.timedelta(days=7),
        "next_week": monday + datetime.timedelta(days=7),
        "this_week": reservations.week_start(today),
    }


def reserve(request, pk):
    """Reservieren – bei freigabepflichtigen Titeln als Anfrage mit Zeitraum."""
    title = get_object_or_404(Title.objects.select_related("category", "team"), pk=pk)
    if not title.lendable:
        messages.error(request, _("Dieser Titel lässt sich nicht reservieren."))
        return redirect("title_detail", pk=title.pk)
    config = SchoolSettings.current()
    kwargs = {
        "capacity": reservations.capacity(title),
        "anonymous": services.anonymous_mode(),
        "approval": title.approval_required,
    }
    days_form = lessons_form = None
    if request.method == "POST":
        if request.POST.get("art") == "stunden":
            form = lessons_form = ReserveLessonsForm(
                request.POST, prefix="stunden", lessons=config.lessons, **kwargs
            )
        else:
            form = days_form = ReserveDaysForm(request.POST, prefix="tage", **kwargs)
        if form.is_valid():
            data = form.cleaned_data
            try:
                if form is lessons_form:
                    start, end, label = reservations.lessons_period(
                        data["day"], data["first"], data["last"], config.lessons
                    )
                else:
                    start, end = reservations.days_period(data["first"], data["last"])
                    label = ""
                if title.approval_required:
                    loan = requests.request_title(
                        title,
                        request.user,
                        message=data.get("message", ""),
                        start=start,
                        end=end,
                        period_label=label,
                    )
                else:
                    created = reservations.reserve(
                        title,
                        request.user,
                        start,
                        end,
                        quantity=data.get("quantity") or 1,
                        label=data.get("borrower_label", ""),
                        period_label=label,
                    )
            except services.LoanError as error:
                form.add_error(None, str(error))
            else:
                if title.approval_required:
                    messages.success(
                        request,
                        _(
                            "Angefragt für %(p)s. %(team)s bekommt Bescheid; der Zeitraum ist "
                            "bis zur Entscheidung vorgemerkt."
                        )
                        % {"p": loan.period_display, "team": services.contact_for(title)},
                    )
                    return redirect("reserve", pk=title.pk)
                messages.success(
                    request,
                    _("Reserviert: %(t)s, %(p)s%(n)s.")
                    % {
                        "t": title.title,
                        "p": created[0].period_display,
                        "n": f" ({len(created)} Exemplare)" if len(created) > 1 else "",
                    },
                )
                return redirect("reserve", pk=title.pk)
    return render(
        request,
        "loans/reserve.html",
        reservation_context(request, title, days_form, lessons_form),
    )


@require_POST
def reservation_cancel(request, pk):
    loan = get_object_or_404(Loan, pk=pk)
    try:
        reservations.cancel(loan, request.user)
    except services.LoanError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, _("Reservierung storniert."))
    return redirect(_safe_local_path(request.POST.get("weiter", ""), reverse("home")))


def label_suggestions(limit=30):
    """Zuletzt verwendete Klassen und Räume als Vorschläge beim Ausleihen."""
    labels = (
        Loan.objects.exclude(borrower_label="")
        .order_by("-created_at")
        .values_list("borrower_label", flat=True)[:300]
    )
    return list(dict.fromkeys(labels))[:limit]


@require_POST
def lend(request, pk):
    copy = get_object_or_404(Copy.objects.select_related("title"), pk=pk)
    for_others = services.can_lend_for_others(request.user, copy.title)
    form = LendForm(request.POST, for_others=for_others, anonymous=services.anonymous_mode())
    if not form.is_valid():
        for errors in form.errors.values():
            messages.error(request, " ".join(errors))
        return redirect("copy_detail", pk=pk)
    borrower = form.cleaned_data.get("borrower") or request.user
    try:
        loan = services.lend(
            copy,
            by=request.user,
            borrower=borrower,
            due_date=form.cleaned_data["due_date"],
            label=form.cleaned_data.get("borrower_label", ""),
        )
    except services.LoanError as error:
        messages.error(request, str(error))
    else:
        if loan.borrower_label:
            who = _(" für %(p)s") % {"p": loan.borrower_label}
        elif borrower == request.user:
            who = ""
        else:
            who = _(" für %(p)s") % {"p": borrower}
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


@require("can_manage_catalog")
def statistics(request):
    key, period = stats.period_from(request.GET)
    data = stats.compute(period)
    if request.GET.get("format") == "xlsx":
        return FileResponse(
            stats.workbook(data),
            as_attachment=True,
            filename=f"fundus-statistik-{period.filename_part}.xlsx",
        )
    params = request.GET.copy()
    params["format"] = "xlsx"
    return render(
        request,
        "loans/statistics.html",
        {
            **data,
            "key": key,
            "presets": stats.presets(),
            "download_query": params.urlencode(),
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
    now = timezone.now()
    result = []
    for loan in loans.order_by("requested_at"):
        if not services.can_lend_for_others(user, loan.title):
            continue
        loan.period_over = bool(loan.reserved_until and loan.reserved_until <= now)
        loan.period_started = bool(loan.reserved_from and loan.reserved_from <= now)
        result.append(loan)
    return result


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
    new_period = None
    if request.POST.get("neu_von"):
        try:
            first = datetime.date.fromisoformat(request.POST["neu_von"])
            last = request.POST.get("neu_bis") or request.POST["neu_von"]
            last = datetime.date.fromisoformat(last)
            new_period = reservations.days_period(first, last)
        except (ValueError, services.LoanError):
            messages.error(request, _("Bitte einen gültigen Zeitraum angeben."))
            return redirect(request.POST.get("weiter") or "home")
    return _request_action(
        request,
        pk,
        lambda loan: requests.approve(loan, by=request.user, new_period=new_period),
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
        loan = requests.hand_over(loan, copy, by=request.user, label=request.POST.get("klasse", ""))
    except services.LoanError as error:
        messages.error(request, str(error))
    else:
        messages.success(
            request,
            _("%(n)s an %(p)s übergeben, bis %(d)s.")
            % {
                "n": copy.inventory_number,
                "p": loan.borrower_display,
                "d": loan.due_date.strftime("%d.%m.%Y"),
            },
        )
    return redirect("copy_detail", pk=copy.pk)
