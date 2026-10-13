import hashlib
import json

from django.db import transaction
from django.utils import timezone

from .models import Content, ContentRevision

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
    return content


@transaction.atomic
def update_content(content, editor, data):

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
    return True
