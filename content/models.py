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
