from django.contrib import admin
from django.contrib.auth.models import Group

from .models import Content, ContentRevision, UserContentState


@admin.register(Content)
class ContentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "content_type",
        "version",
        "last_changed_at",
        "author",
    )
    readonly_fields = ("version", "content_hash", "last_changed_at")


@admin.register(ContentRevision)
class ContentRevisionAdmin(admin.ModelAdmin):
    list_display = ("content", "version", "editor", "changed_fields", "created_at")


@admin.register(UserContentState)
class UserContentStateAdmin(admin.ModelAdmin):
    list_display = ("user", "content", "last_seen_version", "is_watching")


admin.site.unregister(Group)
