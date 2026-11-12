import re

from django import forms

from apps.exam.models import Exam

from .exports import BOOKING_COLUMNS, CANDIDATE_COLUMNS
from .models import User


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


#: https://linkedin.com/in/<name> — with or without "www.", an optional
#: country subdomain (in.linkedin.com) and a trailing slash.
LINKEDIN_RE = re.compile(r"^https://(?:[a-z]{2,3}\.|www\.)?linkedin\.com/in/([\w\-%.]+)/?$", re.IGNORECASE)
#: https://github.com/<username> — a profile, not a repository.
GITHUB_PROFILE_RE = re.compile(r"^https://(?:www\.)?github\.com/([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))/?$")
#: Digits with the usual separators; 7 to 15 digits in all.
PHONE_RE = re.compile(r"^\+?[\d\s\-()]+$")


class ProfileLinksMixin:
    """
    The LinkedIn and GitHub checks, shared by ProfileForm (the profile page)
    and ProfileLinksForm (the exam-completed page), so both accept and refuse
    exactly the same links.
    """

    def clean_linkedin_link(self):
        link = self.cleaned_data["linkedin_link"].strip()
        if link and not LINKEDIN_RE.match(link):
            raise forms.ValidationError("Enter your LinkedIn profile link, e.g. https://www.linkedin.com/in/your-name")
        return link.rstrip("/")

    def clean_github_link(self):
        link = self.cleaned_data["github_link"].strip()
        if link and not GITHUB_PROFILE_RE.match(link):
            raise forms.ValidationError("Enter your GitHub profile link, e.g. https://github.com/your-username")
        return link.rstrip("/")

    @staticmethod
    def github_username_from(link):
        """The username in a GitHub profile link — never typed separately, so the two cannot disagree."""
        match = GITHUB_PROFILE_RE.match(link or "")
        return match.group(1) if match else ""


class ProfileForm(ProfileLinksMixin, forms.ModelForm):
    """
    A user's own details, from /profile/.

    A ModelForm: every field maps onto User, and save() writes them back.
    Only what a person may change about themselves is here. Email and login
    id come from the TestMu AI login and are shown read-only on the page.

    github_username is not a field: it is taken from the GitHub link, so the
    two can never disagree.
    """

    class Meta:
        model = User
        fields = ["display_name", "contact_number", "linkedin_link", "github_link"]
        labels = {
            "display_name": "Full name",
            "contact_number": "Phone",
            "linkedin_link": "LinkedIn profile",
            "github_link": "GitHub profile",
        }
        error_messages = {
            "display_name": {"required": "Enter your name."},
            "linkedin_link": {"invalid": "Enter a full link, starting with https://"},
            "github_link": {"invalid": "Enter a full link, starting with https://"},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Blank on the model (accounts arrive from the login without one),
        # but a person should not save their profile with no name: it is what
        # their certificates print.
        self.fields["display_name"].required = True

    def clean_display_name(self):
        return " ".join(self.cleaned_data["display_name"].split())

    def clean_contact_number(self):
        phone = self.cleaned_data["contact_number"].strip()
        if not phone:
            return ""
        digits = sum(ch.isdigit() for ch in phone)
        if not PHONE_RE.match(phone) or not 7 <= digits <= 15:
            raise forms.ValidationError("Enter a phone number, e.g. +91 98765 43210.")
        return phone

    def save(self, commit=True):
        user = super().save(commit=False)
        user.github_username = self.github_username_from(user.github_link)
        if commit:
            user.save()
        return user


class ProfileLinksForm(ProfileLinksMixin, forms.ModelForm):
    """
    LinkedIn and GitHub from the page a candidate sees after an exam.

    Only fills in what is missing. A link the account already has is not a
    field at all — not shown, not posted, so this page can never clear or
    overwrite it (that is the profile page's job). A link it lacks is
    required, since both are asked for there.
    """

    class Meta:
        model = User
        fields = ["linkedin_link", "github_link"]
        labels = {"linkedin_link": "LinkedIn", "github_link": "GitHub"}
        error_messages = {
            "linkedin_link": {"required": "Enter your LinkedIn profile link.", "invalid": "Enter a full link, starting with https://"},
            "github_link": {"required": "Enter your GitHub profile link.", "invalid": "Enter a full link, starting with https://"},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in list(self.fields):
            if getattr(self.instance, name):
                del self.fields[name]          # already has it: leave it alone
            else:
                self.fields[name].required = True

    def save(self, commit=True):
        user = super().save(commit=False)
        if "github_link" in self.fields:
            user.github_username = self.github_username_from(user.github_link)
        if commit:
            user.save(update_fields=[*self.fields, *(["github_username"] if "github_link" in self.fields else []), "updated_at"])
        return user
