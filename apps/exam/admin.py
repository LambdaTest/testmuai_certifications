from django.contrib import admin

from .models import Booking, Exam


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ("name", "type", "duration_minutes", "level", "status", "slug")
    list_filter = ("type", "level", "status")
    search_fields = ("name", "slug", "external_ref")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = (
        "exam",
        "candidate",
        "scheduled_at",
        "booked_timezone",
        "status",
    )
    list_filter = ("status", "exam")
    search_fields = ("candidate__display_name", "candidate__email")
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "scheduled_at"
