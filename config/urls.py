from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("book/", include("apps.bookings.urls")),
    # Candidates enter at /book from the main TestMu AI site.
    path("", RedirectView.as_view(pattern_name="bookings:book", permanent=False)),
]
