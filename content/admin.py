from django.contrib import admin, messages
from django.contrib.auth.models import Group
from content import services
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

    def save_model(self, request, obj, form, change):
        if change:
            original = Content.objects.get(pk=obj.pk)
            changed = services.update_content(original, request.user, form.cleaned_data)
            if not changed:
                self.message_user(
                    request,
                    "No real change, nothing was saved.",
                    level=messages.WARNING,
                )
        else:
            created = services.create_content(
                request.user, obj.title, obj.body, obj.content_type
            )
            obj.pk = created.pk
        obj.refresh_from_db()


@admin.register(ContentRevision)
class ContentRevisionAdmin(admin.ModelAdmin):
    list_display = ("content", "version", "editor", "changed_fields", "created_at")


@admin.register(UserContentState)
class UserContentStateAdmin(admin.ModelAdmin):
    list_display = ("user", "content", "last_seen_version", "is_watching")


admin.site.unregister(Group)
