import hashlib
import json

from django.db import transaction
from django.utils import timezone

from content.models import Content, ContentRevision, UserContentState

TRACKED_FIELDS = ["title", "body", "content_type"]


def make_hash(title, body, content_type):

    text = json.dumps(
        [title.strip(), body.replace("\r\n", "\n").strip(), content_type],
        ensure_ascii=False,
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@transaction.atomic
def create_content(author, title, body="", content_type="article"):
    content = Content.objects.create(
        author=author,
        title=title,
        body=body,
        content_type=content_type,
        content_hash=make_hash(title, body, content_type),
    )
    ContentRevision.objects.create(
        content=content,
        version=1,
        editor=author,
        title=title,
        body=body,
        content_type=content_type,
        content_hash=content.content_hash,
        changed_fields=TRACKED_FIELDS,
    )
    mark_seen(author, content)
    return content


@transaction.atomic
def update_content(content, editor, data):
    Content.objects.select_for_update().get(pk=content.pk)
    content.refresh_from_db()

    new_values = {
        field: data.get(field, getattr(content, field)) for field in TRACKED_FIELDS
    }
    new_hash = make_hash(**new_values)

    if new_hash == content.content_hash:
        return False

    changed_fields = [
        field
        for field in TRACKED_FIELDS
        if new_values[field] != getattr(content, field)
    ]

    for field, value in new_values.items():
        setattr(content, field, value)
    content.content_hash = new_hash
    content.version += 1
    content.last_changed_at = timezone.now()
    content.save()

    ContentRevision.objects.create(
        content=content,
        version=content.version,
        editor=editor,
        content_hash=new_hash,
        changed_fields=changed_fields,
        **new_values,
    )
    mark_seen(editor, content)

    return True


def start_watching(user, content):

    state, created = UserContentState.objects.get_or_create(
        user=user,
        content=content,
        defaults={"last_seen_version": content.version, "is_watching": True},
    )
    if created:
        return True
    updated = UserContentState.objects.filter(pk=state.pk, is_watching=False).update(
        is_watching=True
    )
    return updated > 0


def stop_watching(user, content):
    UserContentState.objects.filter(user=user, content=content).update(
        is_watching=False
    )


def mark_seen(user, content):

    state, created = UserContentState.objects.get_or_create(
        user=user,
        content=content,
        defaults={"last_seen_version": content.version},
    )
    if not created:
        UserContentState.objects.filter(
            pk=state.pk,
            last_seen_version__lt=content.version,
        ).update(
            last_seen_version=content.version,
            last_seen_at=timezone.now(),
        )
