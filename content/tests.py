from unittest import skipUnless
from unittest.mock import patch

from django.db import connection
from django.test import TransactionTestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from content import services
from content.models import UserContentState, ContentRevision, Content
from users.models import User


class ContentTests(APITestCase):
    def setUp(self):
        self.author = User.objects.create_user("author", password="pw")
        self.user = User.objects.create_user("user", password="pw")
        self.content = services.create_content(self.author, "Title", "Body")

    def test_edit_without_change_does_not_bump_version(self):
        changed = services.update_content(self.content, self.author, {"body": "Body"})
        self.assertFalse(changed)
        self.assertEqual(self.content.version, 1)

    def test_real_edit_bumps_version(self):
        services.update_content(self.content, self.author, {"body": "New"})

        content = Content.objects.get(pk=self.content.pk)
        self.assertEqual(content.version, 2)
        self.assertEqual(content.body, "New")
        revision = ContentRevision.objects.get(content=content, version=2)
        self.assertEqual(revision.body, "New")
        self.assertEqual(revision.editor, self.author)
        self.assertEqual(revision.changed_fields, ["body"])
        self.assertEqual(revision.content_hash, content.content_hash)

    def test_failed_revision_rolls_back_content(self):
        with patch.object(
            ContentRevision.objects, "create", side_effect=RuntimeError("boom")
        ):
            with self.assertRaises(RuntimeError):
                services.update_content(self.content, self.author, {"body": "New"})

        content = Content.objects.get(pk=self.content.pk)
        self.assertEqual(content.version, 1)
        self.assertEqual(content.body, "Body")
        self.assertEqual(ContentRevision.objects.filter(content=content).count(), 1)

    def test_watch_edit_open(self):
        self.client.force_authenticate(self.user)
        self.client.post(f"/api/contents/{self.content.id}/watch/")
        self.assertEqual(self.client.get("/api/me/changes/").json()["count"], 0)

        services.update_content(self.content, self.author, {"body": "New"})
        self.assertEqual(self.client.get("/api/me/changes/").json()["count"], 1)

        self.client.get(f"/api/contents/{self.content.id}/")  # otwarcie = przeczytane
        self.assertEqual(self.client.get("/api/me/changes/").json()["count"], 0)

    def test_only_author_can_edit(self):
        self.client.force_authenticate(self.user)
        response = self.client.patch(f"/api/contents/{self.content.id}/", {"body": "x"})
        self.assertEqual(response.status_code, 403)

    def test_queries_do_not_grow(self):
        self.client.force_authenticate(self.user)

        self.add_changed(2)
        with CaptureQueriesContext(connection) as few:
            self.client.get("/api/me/changes/")

        self.add_changed(20)
        with CaptureQueriesContext(connection) as many:
            self.client.get("/api/me/changes/")

        self.assertEqual(len(few), len(many))

    def add_changed(self, n):
        for i in range(n):
            content = services.create_content(self.author, f"t{i}", "b")
            services.start_watching(self.user, content)
            services.update_content(content, self.author, {"body": "new"})

    def test_start_watching_keeps_earlier_last_seen(self):
        services.mark_seen(self.user, self.content)
        services.update_content(self.content, self.author, {"body": "v2"})
        services.update_content(self.content, self.author, {"body": "v3"})

        services.start_watching(self.user, self.content)

        state = UserContentState.objects.get(user=self.user, content=self.content)
        self.assertEqual(state.last_seen_version, 1)
        self.assertTrue(state.is_watching)

    def test_author_and_editor_have_seen_their_own_version(self):
        state = UserContentState.objects.get(user=self.author, content=self.content)
        self.assertEqual(state.last_seen_version, 1)

        services.update_content(self.content, self.user, {"body": "by user"})
        state = UserContentState.objects.get(user=self.user, content=self.content)
        self.assertEqual(state.last_seen_version, 2)
        self.assertFalse(state.is_watching)

    def test_write_responses_have_user_state(self):
        self.client.force_authenticate(self.author)
        response = self.client.post(
            "/api/contents/", {"title": "T", "body": "B"}, format="json"
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], "up_to_date")
        self.assertFalse(response.json()["is_watching"])

        url = f"/api/contents/{response.json()['id']}/"
        response = self.client.patch(url, {"body": "new"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "up_to_date")
        self.assertEqual(response.json()["versions_behind"], 0)

    def test_changed_fields_uses_same_normalization_as_hash(self):
        content = services.create_content(self.author, "T", "line1\r\nline2")
        services.update_content(
            content, self.author, {"title": "New", "body": "line1\nline2"}
        )
        revision = ContentRevision.objects.get(content=content, version=2)
        self.assertEqual(revision.changed_fields, ["title"])

    def test_detail_shows_state_before_opening_then_marks_seen(self):
        self.client.force_authenticate(self.user)
        url = f"/api/contents/{self.content.id}/"
        self.client.get(url)
        services.update_content(self.content, self.author, {"body": "new"})

        response = self.client.get(url)
        self.assertEqual(response.json()["status"], "updated")
        self.assertEqual(response.json()["versions_behind"], 1)

        response = self.client.get(url)
        self.assertEqual(response.json()["status"], "up_to_date")
        self.assertEqual(response.json()["versions_behind"], 0)

    def test_whitespace_at_edges_and_line_endings_are_not_a_change(self):
        content = services.create_content(self.author, "T", "line1\nline2")
        self.assertFalse(
            services.update_content(content, self.author, {"body": "line1\r\nline2"})
        )
        self.assertFalse(
            services.update_content(
                content, self.author, {"title": "  T  ", "body": "\nline1\nline2  \n"}
            )
        )
        self.assertEqual(content.version, 1)

    def test_whitespace_inside_text_is_a_change(self):
        content = services.create_content(self.author, "T", "a b")
        self.assertTrue(services.update_content(content, self.author, {"body": "a  b"}))
        self.assertEqual(content.version, 2)

    def test_versions_behind_after_many_edits(self):
        self.client.force_authenticate(self.user)
        self.client.post(f"/api/contents/{self.content.id}/watch/")
        for i in range(3):
            services.update_content(self.content, self.author, {"body": f"v{i}"})

        item = self.client.get("/api/me/changes/").json()["results"][0]
        self.assertEqual(item["last_seen_version"], 1)
        self.assertEqual(item["current_version"], 4)
        self.assertEqual(item["versions_behind"], 3)

    def test_unwatch_and_watch_again(self):
        self.client.force_authenticate(self.user)
        url = f"/api/contents/{self.content.id}/watch/"
        self.client.post(url)
        services.update_content(self.content, self.author, {"body": "v2"})
        self.assertEqual(self.client.get("/api/me/changes/").json()["count"], 1)

        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertEqual(self.client.get("/api/me/changes/").json()["count"], 0)

        self.assertEqual(self.client.post(url).status_code, 201)
        self.assertEqual(self.client.get("/api/me/changes/").json()["count"], 1)

    def test_states_of_two_users_are_independent(self):
        other = User.objects.create_user("other", password="pw")
        services.start_watching(self.user, self.content)
        services.start_watching(other, self.content)
        services.update_content(self.content, self.author, {"body": "v2"})

        self.client.force_authenticate(self.user)
        self.client.get(f"/api/contents/{self.content.id}/")
        self.assertEqual(self.client.get("/api/me/changes/").json()["count"], 0)

        self.client.force_authenticate(other)
        self.assertEqual(self.client.get("/api/me/changes/").json()["count"], 1)

    def test_user_changes_endpoint_permissions(self):
        staff = User.objects.create_user("staff", password="pw", is_staff=True)
        services.start_watching(self.user, self.content)
        services.update_content(self.content, self.author, {"body": "v2"})
        url = f"/api/admin/users/{self.user.id}/changes/"

        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get(url).status_code, 403)

        self.client.force_authenticate(staff)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(
            self.client.get("/api/admin/users/99999/changes/").status_code, 404
        )

    def test_list_and_history_do_not_mark_as_seen(self):
        self.client.force_authenticate(self.user)
        services.start_watching(self.user, self.content)
        services.update_content(self.content, self.author, {"body": "v2"})

        self.client.get("/api/contents/")
        self.client.get(f"/api/contents/{self.content.id}/history/")

        state = UserContentState.objects.get(user=self.user, content=self.content)
        self.assertEqual(state.last_seen_version, 1)
        self.assertEqual(self.client.get("/api/me/changes/").json()["count"], 1)

    def test_mark_seen_never_goes_back(self):
        services.update_content(self.content, self.author, {"body": "v2"})
        services.update_content(self.content, self.author, {"body": "v3"})
        services.mark_seen(self.user, self.content)

        old_content = Content.objects.get(pk=self.content.pk)
        old_content.version = 2
        stale_state = UserContentState.objects.get(user=self.user, content=self.content)
        stale_state.last_seen_version = 1

        with patch.object(
            UserContentState.objects, "get_or_create", return_value=(stale_state, False)
        ):
            services.mark_seen(self.user, old_content)

        state = UserContentState.objects.get(user=self.user, content=self.content)
        self.assertEqual(state.last_seen_version, 3)

    def test_mark_seen_does_not_restore_watching(self):
        services.start_watching(self.user, self.content)
        services.update_content(self.content, self.author, {"body": "v2"})
        stale_state = UserContentState.objects.get(user=self.user, content=self.content)

        services.stop_watching(self.user, self.content)

        with patch.object(
            UserContentState.objects, "get_or_create", return_value=(stale_state, False)
        ):
            services.mark_seen(self.user, self.content)

        state = UserContentState.objects.get(user=self.user, content=self.content)
        self.assertFalse(state.is_watching)
        self.assertEqual(state.last_seen_version, 2)

    def test_start_watching_does_not_overwrite_last_seen(self):
        services.update_content(self.content, self.author, {"body": "v2"})
        services.update_content(self.content, self.author, {"body": "v3"})
        services.mark_seen(self.user, self.content)

        stale_state = UserContentState.objects.get(user=self.user, content=self.content)
        stale_state.last_seen_version = 1

        with patch.object(
            UserContentState.objects, "get_or_create", return_value=(stale_state, False)
        ):
            services.start_watching(self.user, self.content)

        state = UserContentState.objects.get(user=self.user, content=self.content)
        self.assertEqual(state.last_seen_version, 3)
        self.assertTrue(state.is_watching)

    @skipUnless(connection.vendor == "postgresql", "row locks need PostgreSQL")
    def test_update_content_locks_the_row(self):
        with CaptureQueriesContext(connection) as queries:
            services.update_content(self.content, self.author, {"body": "New"})

        sql = " ".join(query["sql"] for query in queries)
        self.assertIn("FOR UPDATE", sql)
