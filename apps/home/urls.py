from django.urls import path
from django.views.generic import RedirectView
from . import views

app_name = "home"

urlpatterns = [
    # Candidates enter at /book from the main TestMu AI site. The dashboard
    # will live here once there is something to show.
    path("", RedirectView.as_view(pattern_name="exam:book", permanent=False), name="index"),
    path("dashboard/", views.dashboard, name="dashboard"),
]
