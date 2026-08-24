from django.contrib import admin

from .models import (
    AnswerOptions,
    Audio,
    Exam,
    ExamBooking,
    Image,
    Question,
    Subject,
    Video,
)


class CreatedByMixin:
    """Stamps created_by from the logged-in user so it isn't hand-picked."""

    def save_model(self, request, obj, form, change):
        if not change and getattr(obj, "created_by_id", None) is None:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    def get_exclude(self, request, obj=None):
        return ["created_by"]


@admin.register(Subject)
class SubjectAdmin(CreatedByMixin, admin.ModelAdmin):
    list_display = ("name", "slug", "created_at")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


class AnswerOptionsInline(admin.TabularInline):
    model = AnswerOptions
    extra = 4
    exclude = ["created_by"]


@admin.register(Question)
class QuestionAdmin(CreatedByMixin, admin.ModelAdmin):
    list_display = ("__str__", "question_subject", "question_type", "question_difficulty", "marks")
    list_filter = ("question_type", "question_difficulty", "question_subject")
    search_fields = ("question_text", "question_keywords", "question_tags")
    inlines = [AnswerOptionsInline]

    def save_formset(self, request, form, formset, change):
        # Inline answer options need created_by too.
        for obj in formset.save(commit=False):
            if getattr(obj, "created_by_id", None) is None:
                obj.created_by = request.user
            obj.save()
        for obj in formset.deleted_objects:
            obj.delete()
        formset.save_m2m()


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ("exam_name", "subject", "exam_type", "duration_minutes", "status", "slug")
    list_filter = ("exam_type", "status", "subject")
    search_fields = ("exam_name", "slug", "external_ref")
    prepopulated_fields = {"slug": ("exam_name",)}


@admin.register(ExamBooking)
class ExamBookingAdmin(admin.ModelAdmin):
    list_display = ("exam", "candidate", "scheduled_at", "booked_timezone", "status")
    list_filter = ("status", "exam")
    search_fields = ("candidate__display_name", "candidate__email", "booking_id")
    readonly_fields = ("booking_id", "created_at", "updated_at")
    date_hierarchy = "scheduled_at"


for model in (Image, Audio, Video):
    admin.site.register(model)
