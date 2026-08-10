"""
Cross-cutting pages — the candidate dashboard and, later, account settings.

Anything about certifications, booking, sitting an exam, grading, or
credentials belongs in ``apps.exam``.
"""

from django.shortcuts import render


def dashboard(request):
    # The template is still static sample markup. Each block that should read
    # real data names its context variable in a comment above it.
    return render(request, "home/dashboard_candidate.html")
