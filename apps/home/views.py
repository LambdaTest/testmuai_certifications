"""
Cross-cutting pages — the candidate dashboard and, later, account settings.

Anything about certifications, booking, sitting an exam, grading, or
credentials belongs in ``apps.exam``.
"""

from django.shortcuts import render
from django.contrib.auth.decorators import login_required

@login_required
def dashboard(request):
    # The template is still static sample markup. Each block that should read
    # real data names its context variable in a comment above it.
    user_role = request.user.role
    if user_role == "admin" or user_role == "examiner":
        return render(request, "home/dashboard_admin.html")
    elif user_role == "candidate":
        return render(request, "home/dashboard_candidate.html")
    else:
        return render(request, "home/404.html")
