from django.contrib import admin

from .models import Booking, Certification


@admin.register(Certification)
class CertificationAdmin(admin.ModelAdmin):
    list_display = ("name", "level", "status", "slug", "external_ref")
    list_filter = ("level", "status")
    search_fields = ("name", "slug", "external_ref")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = (
        "certification",
        "candidate",
        "scheduled_at",
        "booked_timezone",
        "status",
    )
    list_filter = ("status", "certification")
    search_fields = ("candidate__display_name", "candidate__email")
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "scheduled_at"
