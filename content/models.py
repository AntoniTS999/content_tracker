from django.conf import settings
from django.db import models
from django.utils import timezone


class Content(models.Model):
    class Type(models.TextChoices):
        ARTICLE = "article", "Article"
        OFFER = "offer", "Offer"
        DOCUMENT = "document", "Document"
        OTHER = "other", "Other"

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="contents",
    )
    content_type = models.CharField(
        max_length=20, choices=Type.choices, default=Type.ARTICLE
    )
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True)

    version = models.PositiveIntegerField(default=1)
    content_hash = models.CharField(max_length=64, blank=True)
    last_changed_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-last_changed_at", "-id"]

    def __str__(self):
        return f"{self.title} - version {self.version}"


class ContentRevision(models.Model):
    """Unchangeable copy (version history)"""

    content = models.ForeignKey(
        Content, on_delete=models.CASCADE, related_name="revisions"
    )
    version = models.PositiveIntegerField()
    editor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField(default=timezone.now)

    content_type = models.CharField(max_length=20, choices=Content.Type.choices)
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True)
    content_hash = models.CharField(max_length=64)

    changed_fields = models.JSONField(default=list)

    class Meta:
        ordering = ["version"]
        constraints = [
            models.UniqueConstraint(
                fields=["content", "version"], name="unique_revision_content_version"
            ),
        ]

    def __str__(self):
        return f"{self.content.id} - version: {self.version}"
