from django import forms

from fundus.core.models import SchoolSettings


class SchoolSettingsForm(forms.ModelForm):
    class Meta:
        model = SchoolSettings
        fields = [
            "number_prefix",
            "number_digits",
            "next_number",
            "outdated_norm_years",
            "isbn_lookup_enabled",
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
