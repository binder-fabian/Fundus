from django import forms

from fundus.core.models import SchoolSettings


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
            "reorder_email",
            "anonymize_after_days",
            "history_names_days",
            "label_offset_x",
            "label_offset_y",
        ]
        widgets = {
            "number_digits": forms.NumberInput(attrs={"min": 1, "max": 10}),
        }

    def clean_number_digits(self):
        digits = self.cleaned_data["number_digits"]
        if not 1 <= digits <= 10:
            raise forms.ValidationError("Bitte 1 bis 10 Stellen wählen.")
        return digits

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
