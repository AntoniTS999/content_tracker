from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from content import services
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
