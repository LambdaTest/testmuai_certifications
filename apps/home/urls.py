from django.urls import path
from django.views.generic import RedirectView
from . import views

app_name = "home"

urlpatterns = [
    # Candidates enter at /book from the main TestMu AI site. The dashboard
    # will live here once there is something to show.
    path("", RedirectView.as_view(pattern_name="exam:book", permanent=False), name="index"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("candidates/", views.candidate_info, name="candidate_info"),
    path("candidate_detail/<int:candidate_id>/", views.candidate_detail, name="candidate_detail"),
    path("export_candidates/", views.export_candidates, name="export_candidates"),
]
