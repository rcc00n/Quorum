from django.contrib.auth.models import User
from django.test import TestCase, Client
from unittest.mock import patch
from .models import Preference


class PortalTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            "reader", password="A-clear-perspective-928!"
        )

    def post(self, path, data):
        return self.client.post(
            "/api/" + path + "/", data, content_type="application/json"
        )

    def test_session_and_csrf(self):
        c = Client(enforce_csrf_checks=True)
        self.assertIsNone(c.get("/api/session/").json()["user"])
        self.assertEqual(
            c.post("/api/login/", {}, content_type="application/json").status_code, 403
        )
        token = c.get("/api/session/").json()["csrfToken"]
        r = c.post(
            "/api/login/",
            {"username": "reader", "password": "A-clear-perspective-928!"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.cookies["quorum_session"]["httponly"])

    def test_registration_and_logout(self):
        self.assertEqual(
            self.post(
                "register",
                {"username": "newreader", "password": "A-new-perspective-926!"},
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.get("/api/session/").json()["user"]["username"], "newreader"
        )
        self.assertEqual(self.post("logout", {}).status_code, 200)
        self.assertEqual(self.client.get("/api/feed/").status_code, 401)

    def test_password_and_profile(self):
        self.client.force_login(self.user)
        self.assertEqual(
            self.post(
                "profile", {"name": "Reader", "email": "r@example.com"}
            ).status_code,
            200,
        )
        self.assertEqual(
            self.post(
                "password",
                {
                    "old_password": "wrong",
                    "new_password1": "A-new-perspective-926!",
                    "new_password2": "A-new-perspective-926!",
                },
            ).status_code,
            400,
        )
        self.assertEqual(
            self.post(
                "password",
                {
                    "old_password": "A-clear-perspective-928!",
                    "new_password1": "A-new-perspective-926!",
                    "new_password2": "A-new-perspective-926!",
                },
            ).status_code,
            200,
        )
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("A-new-perspective-926!"))
        self.assertEqual(self.client.get("/api/feed/").status_code, 200)

    def test_preferences_and_empty_feed(self):
        self.client.force_login(self.user)
        self.assertEqual(
            self.post("preferences", {"topics": ["invented"]}).status_code, 400
        )
        self.assertEqual(self.post("preferences", {"topics": []}).status_code, 200)
        self.assertEqual(Preference.objects.get(user=self.user).topics, [])
        self.assertEqual(self.client.get("/api/feed/").json()["events"], [])
        self.assertEqual(self.client.get("/api/feed/?date=bad").status_code, 400)

    def test_abuse_limit(self):
        for i in range(20):
            self.post("login", {"username": "reader", "password": "wrong"})
        self.assertEqual(
            self.post("login", {"username": "reader", "password": "wrong"}).status_code,
            429,
        )

    def test_staff_boundaries(self):
        self.assertEqual(self.client.get("/staff/").status_code, 302)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get("/staff/status/").status_code, 302)
        self.user.is_staff = True
        self.user.save()
        self.assertEqual(self.client.get("/staff/").status_code, 200)
        self.assertEqual(self.client.get("/staff/auth/user/").status_code, 403)
        for p in ["topics", "sources", "status", "integrations"]:
            self.assertEqual(self.client.get("/staff/" + p + "/").status_code, 200)

    def test_superuser_admin(self):
        root = User.objects.create_superuser(
            "owner", password="A-clear-perspective-928!"
        )
        self.client.force_login(root)
        for p in ["auth/user/", "auth/user/add/", "portal/preference/"]:
            self.assertEqual(self.client.get("/staff/" + p).status_code, 200)

    def test_invalid_json_and_methods(self):
        self.assertEqual(self.client.get("/api/login/").status_code, 405)
        self.assertEqual(
            self.client.post(
                "/api/login/", "[]", content_type="application/json"
            ).status_code,
            400,
        )

    def test_topic_selection_persists(self):
        self.client.force_login(self.user)
        with patch("portal.views.adapter") as adapter:
            adapter.snapshot.return_value = {
                "status": "demo",
                "topics": [{"id": "demo", "name": "DEMO topic"}],
                "sources": [],
                "events": [],
                "digests": [],
            }
            self.assertEqual(
                self.post("preferences", {"topics": ["demo", "demo"]}).status_code, 200
            )
        self.client.logout()
        self.client.force_login(self.user)
        self.assertEqual(
            self.client.get("/api/session/").json()["user"]["topics"], ["demo"]
        )

    def test_staff_login_abuse_limit(self):
        from .limits import consume_attempt
        from django.test import RequestFactory

        request = RequestFactory().post("/staff/login/")
        for _ in range(20):
            consume_attempt(request)
        self.assertEqual(
            self.client.post(
                "/staff/login/", {"username": "reader", "password": "wrong"}
            ).status_code,
            429,
        )

    def test_staff_login_redirect(self):
        User.objects.create_superuser(
            "staff-login", password="A-clear-perspective-928!"
        )
        response = self.client.post(
            "/staff/login/",
            {"username": "staff-login", "password": "A-clear-perspective-928!"},
        )
        self.assertRedirects(response, "/staff/")
