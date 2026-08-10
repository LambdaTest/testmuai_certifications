"""
Cross-cutting pages — the candidate dashboard and, later, account settings.

Anything about certifications, booking, sitting an exam, grading, or
credentials belongs in ``apps.exam``.
"""

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import Http404

@login_required
def dashboard(request):
    # The template is still static sample markup. Each block that should read
    # real data names its context variable in a comment above it.
    try:
        user_role = request.user.role
        user_name = request.user.display_name
        user_name = user_name.split(" ")[0]  # Get first name only
    except AttributeError:
        user_role = None
        user_name = None
    if user_role == "admin" or user_role == "examiner":
        return render(request, "home/dashboard_admin.html", {"user_name": user_name, "user_role": user_role})
    elif user_role == "candidate":
        return render(request, "home/dashboard_candidate.html", {"user_name": user_name, "user_role": user_role})
    else:
        # Raising is what actually produces a 404 — Django then renders
        # templates/404.html with a 404 status. Rendering that template
        # directly would return HTTP 200 with a "not found" page on it.
        raise Http404("No dashboard for this role.")
