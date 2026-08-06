from django.contrib import admin

from .models import Certification


@admin.register(Certification)
class CertificationAdmin(admin.ModelAdmin):
    list_display = ("name", "level", "status", "slug", "external_ref")
    list_filter = ("level", "status")
    search_fields = ("name", "slug", "external_ref")
    prepopulated_fields = {"slug": ("name",)}
