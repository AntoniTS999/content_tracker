# contenttracker

Simple Django + DRF backend where users can watch content (articles, offers, documents)
and see what changed since they last opened it.

## Run

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
python manage.py test content
```

Create test users in the admin panel (`/admin/`).

- Swagger: http://127.0.0.1:8000/api/v1/schema/swagger-ui/
- Schema (for Postman): http://127.0.0.1:8000/api/schema/

## Authentication

The API uses JWT (`djangorestframework-simplejwt`).

1. Get tokens: `POST /api/token/` with `{"username": "...", "password": "..."}`
   -> returns `access` and `refresh`
2. Send the access token in every request: `Authorization: Bearer <access>`
3. When the access token expires, get a new one: `POST /api/token-refresh/` with `{"refresh": "..."}`

You can check if a token is still valid with `POST /api/token-verify` and `{"token": "..."}`.

In Swagger: call `/api/token/`, copy the `access` token, click **Authorize** and paste it.
In Postman: Authorization tab -> Bearer Token.

To check what changed for a user X:
- log in as X and call `GET /api/me/changes/`
- or as admin call `GET /api/admin/users/{id}/changes/`

## Endpoints

| Method | Path | What it does |
|---|---|---|
| POST | `/api/token/` | log in, returns JWT `access` and `refresh` |
| POST | `/api/token-refresh/` | get a new `access` token |
| POST | `/api/token-verify` | check if a token is valid |
| GET | `/api/contents/` | list of content, with `is_watching`, `status` (`unseen` / `updated` / `up_to_date`) and `versions_behind` for the current user |
| POST | `/api/contents/` | create content |
| GET | `/api/contents/{id}/` | detail, **marks the content as read** |
| PUT/PATCH | `/api/contents/{id}/` | edit (only author or staff) |
| POST / DELETE | `/api/contents/{id}/watch/` | start / stop watching |
| GET | `/api/contents/{id}/history/` | list of versions: who changed, when, which fields, `is_new` for the user |
| GET | `/api/me/changes/` | watched content that changed since I last read it |
| GET | `/api/admin/users/{id}/changes/` | same for any user (admin only) |

## How it works

**What is a change?** A change is when the title, the body or the type of the content is different than before.
Then the content gets a new version (`Content.version` goes up by 1) and a copy is saved in
`ContentRevision`, together with the list of changed fields.

Before comparing, we clean the text removing spaces and new lines from the start and the
end of `title` and `body`, and change `\r\n` to `\n` in `body`. Spaces and empty lines in the
middle of the text are not removed, so they count as a change. Then we make a hash of the cleaned
fields and compare it with the saved hash.

If the hash is the same, the edit is rejected. Nothing is saved, there is no new version and no
notification. So if someone only adds a space or an enter at the end of the text, it is not saved
at all. It was done that way to keep the history clean and to avoid fake notifications.

The downside is that some formats need those spaces. For example, in Markdown two spaces at the
end of a line make a line break. For such formats the cleaning should be smaller.

**Per-user state.** `UserContentState` keeps `last_seen_version` and `is_watching` for each
(user, content) pair. Content is "changed" for a user when `content.version > last_seen_version`.
Opening the detail endpoint sets `last_seen_version` to the current version.
The list, history and changes endpoints do not mark anything as read.

Details:
- when you start watching, the current version is your starting point (you only see changes made after)
- if you stop and start watching again, the old `last_seen_version` stays, so you see what changed in between
- if you edit content yourself, it is not shown as a change for you

**Why a version number and not `updated_at`?** A number is simple to compare, it does not depend
on clocks, and it also tells how many versions the user missed.

**Edge case: content changed a few times while the user was away.**
The API returns a flag (`status: updated`), the number of missed versions (`versions_behind`)
and the history with changed fields. Just a flag is too little (one typo and 7 edits look the same),
and full diffs would be more work and more data, so I skipped them. The full text of every
version is saved in `ContentRevision`, so diffs can be added later.

## Performance

- **Nothing is written per watcher on edit.** An edit changes one content row and adds one revision.
  It does not matter if 10 or 10,000 people watch it. (The other way, creating an "unread" row for
  every watcher on every edit, would be a lot of writes.)
- **Changes list is one query.** `/api/me/changes/` takes the user's watched items and compares
  `content.version > last_seen_version` in SQL (with `F()`), plus `select_related("content")`.
  There is an index on `(user, is_watching)`.
- **No N+1.** The content list loads the user's states for the whole page in one query.
  Authors are loaded with `select_related`. The test `test_queries_do_not_grow` checks that the
  number of queries is the same for few and for many items.
- **Pagination** is on (10 per page).
- **Cache** (not done, an idea): a cached counter "you have N changes" per user with a short
  timeout, cleared when the user opens, watches or unwatches something. I would not cache the
  list itself.

**What will be the bottleneck?**
- `UserContentState` grows with users x content, so old rows would need cleanup later
- `ContentRevision` stores full copies, so with big content and many edits it needs diffs or cleanup
- `count()` in pagination on very long lists (could use cursor pagination)
- sending notifications (if added) should be done in the background, e.g. Celery
- title search with `icontains` would need full-text search

## Concurrency

Two edits of the same content at the same moment could get the same version number.
`UNIQUE(content, version)` stops this: the second one fails instead of making a duplicate.
For production I would add `select_for_update()` in `update_content` so the edits go one by one.
`last_seen_version` is updated with a conditional UPDATE (WHERE last_seen_version < new), so a slow older request can never move it back.


## Simplifications

- `GET /contents/{id}/` marks content as read (that is how the task describes it).
  `/history/` can be used to look without marking.
- A -> B -> A counts as 2 versions, even if the text is the same as the user saw.
- No registration, content deleting or notifications. Users are created in the admin.