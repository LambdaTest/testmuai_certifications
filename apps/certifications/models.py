"""
Certification products.

This app is the source of truth for them — the main TestMu AI site holds only
marketing pages on top. Exam versions, sections and the question bank come
later; this is the minimum the booking page needs.
"""

from django.db import models


class Certification(models.Model):
    class Level(models.TextChoices):
        BEGINNER = "beginner", "Beginner"
        ADVANCED = "advanced", "Advanced"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"

    name = models.CharField(max_length=255)

    #: Mirrors the slug the main site already uses in its catalog URLs
    #: (testmuai.com/certifications/<slug>/). Internal — changing it breaks
    #: nothing externally, but keeping them aligned gives both systems one
    #: vocabulary.
    slug = models.SlugField(max_length=255, unique=True)

    level = models.CharField(max_length=16, choices=Level.choices)
    description = models.TextField(blank=True)
    icon_url = models.URLField(blank=True)

    #: Link to the main site's detail page, for "learn more".
    marketing_url = models.URLField(blank=True)

    #: TestMu AI's own numeric course id, as passed by the current redirect
    #: (?id=2934). Nullable and unused for now — it exists so a prefill hint
    #: can be mapped later without a migration.
    external_ref = models.CharField(max_length=64, blank=True, null=True, db_index=True)

    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.DRAFT
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "certifications"
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def is_bookable(self) -> bool:
        # Once exam versions exist this also requires a published version.
        return self.status == self.Status.PUBLISHED
