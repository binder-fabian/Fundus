from django import forms

from fundus.core.models import SchoolSettings, parse_lesson_times


class SchoolSettingsForm(forms.ModelForm):
    school_name = forms.CharField(
        label="Name der Schule",
        max_length=200,
        help_text="Erscheint z. B. auf dem Plakat.",
    )

    class Meta:
        model = SchoolSettings
        fields = [
            "number_prefix",
            "number_digits",
            "next_number",
            "outdated_norm_years",
            "isbn_lookup_enabled",
            "reminders_enabled",
            "reminder_days_before",
            "overdue_notice_days",
            "escalate_days",
            "request_reminder_days",
            "request_pickup_days",
            "lesson_times",
            "reservation_reminders",
            "reorder_email",
            "borrower_visibility",
            "anonymous_lending",
            "anonymize_after_days",
            "history_names_days",
            "sso_create_accounts",
            "sso_domains",
            "password_login",
            "backup_interval",
            "backup_keep",
            "label_offset_x",
            "label_offset_y",
        ]
        widgets = {
            "number_digits": forms.NumberInput(attrs={"min": 1, "max": 10}),
            "lesson_times": forms.Textarea(attrs={"rows": 8, "cols": 16}),
        }

    def clean_number_digits(self):
        digits = self.cleaned_data["number_digits"]
        if not 1 <= digits <= 10:
            raise forms.ValidationError("Bitte 1 bis 10 Stellen wählen.")
        return digits

    def clean_lesson_times(self):
        text = self.cleaned_data["lesson_times"]
        try:
            lessons = parse_lesson_times(text)
        except ValueError as error:
            raise forms.ValidationError(str(error)) from None
        if not lessons:
            raise forms.ValidationError("Bitte mindestens eine Stunde angeben.")
        return "\n".join(f"{start:%H:%M}-{end:%H:%M}" for _n, start, end in lessons)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["school_name"].initial = self.instance.school.name

    def save(self, commit=True):
        school = self.instance.school
        school.name = self.cleaned_data["school_name"]
        school.save()
        return super().save(commit)

    def clean(self):
        cleaned = super().clean()
        overdue, escalate = cleaned.get("overdue_notice_days"), cleaned.get("escalate_days")
        if overdue is not None and escalate is not None and escalate < overdue:
            self.add_error("escalate_days", "Sollte nicht vor dem Überfällig-Hinweis liegen.")
        return cleaned
