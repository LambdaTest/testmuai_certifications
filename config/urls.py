from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.exam.urls")),
    path("", include("apps.home.urls")),
]

# Uploaded media, served by Django in development only.
#
# static() returns an empty list when DEBUG is False, so this is self-disabling
# rather than a footgun — but the reason matters: Django serving user-uploaded
# files in production is slow and a security risk, since anything under
# MEDIA_ROOT becomes reachable. In production S3 (or a web server) serves them.
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
