from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from content import services
from content.models import UserContentState, ContentRevision
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
        self.assertEqual(self.content.version, 2)

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
