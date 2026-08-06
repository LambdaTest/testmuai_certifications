from django.contrib import admin

from .models import User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("display_name", "email", "role", "external_id", "created_at")
    list_filter = ("role", "is_staff")
    search_fields = ("display_name", "email", "external_id")
    readonly_fields = ("external_id", "created_at", "updated_at")
