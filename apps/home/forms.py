from django import forms

from apps.exam.models import Exam

from .exports import BOOKING_COLUMNS, CANDIDATE_COLUMNS


def _choices(columns):
    return [(key, header) for key, (header, _) in columns.items()]


class ExportCandidatesForm(forms.Form):
    """
    Candidate Center → Export Candidates: which export, which rows, which
    columns.

    The page is a GET form, so filters and choices sit in the URL and come
    back ticked when the page is shown again ("Nothing matches"). Nothing here
    saves anything.

    Columns are two MultipleChoiceFields, one per export, since each has its
    own list. A MultipleChoiceField accepts only keys in its `choices` — any
    other value is a form error — which is what keeps the CSV to the fixed
    columns in apps.home.exports. Only the list for the chosen export is
    used; the other is ignored. Neither is required: the locked columns
    (email; email and exam) are always written, so ticking nothing is still a
    useful file.
    """

    kind = forms.ChoiceField(
        choices=[("candidates", "One row per candidate"), ("bookings", "One row per booking")],
        initial="candidates",
        widget=forms.RadioSelect,
        error_messages={"required": "Choose what to export.", "invalid_choice": "Choose what to export."},
    )
    #: Every exam, not only published ones — an exam since withdrawn still has
    #: bookings worth exporting. Blank means All exams.
    exam = forms.ModelChoiceField(
        queryset=Exam.objects.order_by("exam_name"),
        required=False,
        empty_label="All exams",
        error_messages={"invalid_choice": "That exam no longer exists."},
    )
    date_from = forms.DateField(required=False, error_messages={"invalid": "Enter a valid From date."})
    date_to = forms.DateField(required=False, error_messages={"invalid": "Enter a valid To date."})
    candidate_columns = forms.MultipleChoiceField(
        choices=_choices(CANDIDATE_COLUMNS), required=False, widget=forms.CheckboxSelectMultiple,
    )
    booking_columns = forms.MultipleChoiceField(
        choices=_choices(BOOKING_COLUMNS), required=False, widget=forms.CheckboxSelectMultiple,
    )

    def clean(self):
        # Runs after every field's own checks, so the dates here are real
        # dates or None — a field that failed is simply missing.
        cleaned = super().clean()
        date_from = cleaned.get("date_from")
        date_to = cleaned.get("date_to")
        # The page keeps To disabled until From is picked; this is the check
        # that holds, since the URL can be typed by hand.
        if date_to and not date_from:
            self.add_error("date_from", "Pick a From date before a To date.")
        elif date_from and date_to and date_to < date_from:
            self.add_error("date_to", "To cannot be before From.")
        return cleaned

    def chosen_columns(self):
        """The optional columns ticked for the chosen export. Call after is_valid()."""
        key = "candidate_columns" if self.cleaned_data["kind"] == "candidates" else "booking_columns"
        return set(self.cleaned_data[key])
