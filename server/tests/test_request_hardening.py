"""Debugger opt-in and JSON body checks for the four routes that used to 500.

No network and no model keys. Bad bodies must be JSON 400s with no traceback.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER = Path(__file__).resolve().parents[1]
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

import config  # noqa: E402
import store  # noqa: E402
from app import app, cart_by_session, sessions  # noqa: E402

LOW_RISK = {
    "risk": "low",
    "reason": "test",
    "suggested_scopes": ["view", "act"],
    "drop_act": False,
}
_DEBUG_ENV = ("FLASK_DEBUG", "DEBUG", "AURIF_ENV", "PORT")
_ROUTES = ("/ai/handshake", "/ai/actions", "/api/auth/signup", "/api/sites")
_OBJECT_ERROR = "request body must be a JSON object"
_SENTINEL = "sentinel-exc-9f3c"


def _no_traceback(testcase: unittest.TestCase, response) -> None:
    text = response.get_data(as_text=True).lower()
    testcase.assertNotIn("traceback", text)
    testcase.assertNotIn("debugger", text)
    testcase.assertNotIn(_SENTINEL, text)
    testcase.assertIn("application/json", response.content_type)


class FlaskDebugTests(unittest.TestCase):
    def setUp(self):
        self._saved = {name: os.environ.get(name) for name in _DEBUG_ENV}
        for name in _DEBUG_ENV:
            os.environ.pop(name, None)

    def tearDown(self):
        for name, value in self._saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def test_debug_is_off_by_default(self):
        self.assertFalse(config.flask_debug())

    def test_debug_is_on_with_flask_debug_1(self):
        os.environ["FLASK_DEBUG"] = "1"
        self.assertTrue(config.flask_debug())

    def test_debug_is_on_with_flask_debug_true(self):
        os.environ["FLASK_DEBUG"] = "true"
        self.assertTrue(config.flask_debug())

    def test_debug_alias_still_enables_the_debugger(self):
        os.environ["DEBUG"] = "1"
        self.assertTrue(config.flask_debug())

    def test_flask_debug_zero_stays_off_even_if_debug_alias_is_set(self):
        os.environ["FLASK_DEBUG"] = "0"
        os.environ["DEBUG"] = "true"
        self.assertFalse(config.flask_debug())

    def test_port_and_production_do_not_turn_debug_on(self):
        os.environ["PORT"] = "8787"
        self.assertFalse(config.flask_debug())
        os.environ["AURIF_ENV"] = "production"
        self.assertFalse(config.flask_debug())


class JsonBodyTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        store_path = Path(self._tmpdir.name) / "store.json"
        self._store_patch = patch.object(store, "STORE_PATH", store_path)
        self._store_patch.start()
        self.addCleanup(self._store_patch.stop)
        self._risk_patch = patch("muse_client.score_purpose", return_value=LOW_RISK)
        self._risk_patch.start()
        self.addCleanup(self._risk_patch.stop)
        sessions.clear()
        cart_by_session.clear()
        store.load()
        self.client = app.test_client()
        self.site_key = store.get_site("demo-shop")["site_key"]

    def _owner(self) -> str:
        response = self.client.post(
            "/api/auth/login",
            json={"email": "owner@aurif.dev", "password": "demo1234"},
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()["token"]

    def _assert_json_400(self, response, *needles: str):
        self.assertEqual(response.status_code, 400, response.get_data(as_text=True))
        _no_traceback(self, response)
        body = response.get_json()
        self.assertIsInstance(body, dict)
        for needle in needles:
            self.assertIn(needle, body["error"])
        return body

    def test_list_body_is_400_on_each_route(self):
        for path in _ROUTES:
            with self.subTest(path=path):
                response = self.client.post(path, json=[1, 2])
                body = self._assert_json_400(response, _OBJECT_ERROR)
                self.assertEqual(body, {"error": _OBJECT_ERROR})

    def test_string_body_is_400_on_each_route(self):
        for path in _ROUTES:
            with self.subTest(path=path):
                response = self.client.post(path, json="hello")
                body = self._assert_json_400(response, _OBJECT_ERROR)
                self.assertEqual(body, {"error": _OBJECT_ERROR})

    def test_wrong_field_type_is_400_and_names_the_field(self):
        cases = (
            ("/ai/handshake", {"purpose": 5}, "purpose"),
            ("/ai/handshake", {"requested_scopes": "view"}, "requested_scopes"),
            ("/ai/actions", {"action_id": 5}, "action_id"),
            ("/ai/actions", {"action_id": "nav.home", "args": [1]}, "args"),
            (
                "/api/auth/signup",
                {"email": "person@example.com", "password": 5, "name": "Person"},
                "password",
            ),
            ("/api/sites", {"name": 5}, "name"),
            ("/api/sites", {"url": {"host": "example.com"}}, "url"),
        )
        for path, payload, field in cases:
            with self.subTest(path=path, field=field):
                response = self.client.post(path, json=payload)
                body = self._assert_json_400(response, field)
                self.assertNotEqual(body["error"], _OBJECT_ERROR)
                self.assertFalse(body["ok"])

    def test_valid_requests_still_succeed(self):
        handshake = self.client.post(
            "/ai/handshake",
            json={
                "agent_id": "qa",
                "agent_version": "1.2.3",
                "purpose": "browse",
                "requested_scopes": ["view"],
            },
            headers={"X-Aurif-Site-Key": self.site_key},
        )
        self.assertEqual(handshake.status_code, 200, handshake.get_json())
        token = handshake.get_json()["session_token"]
        self.assertEqual(handshake.get_json()["granted_scopes"], ["view"])

        # JSON null still means "use the default", same as an omitted field.
        null_purpose = self.client.post(
            "/ai/handshake",
            json={"purpose": None, "requested_scopes": ["view"]},
            headers={"X-Aurif-Site-Key": self.site_key},
        )
        self.assertEqual(null_purpose.status_code, 200, null_purpose.get_json())

        action = self.client.post(
            "/ai/actions",
            json={"action_id": "nav.home", "args": {}},
            headers={"X-Aurif-Site-Key": self.site_key, "X-Aurif-Session": token},
        )
        self.assertEqual(action.status_code, 200, action.get_json())
        self.assertTrue(action.get_json()["ok"])

        # A well-typed body with no site key is still rejected by the key check.
        missing_key = self.client.post(
            "/ai/handshake",
            json={"purpose": "browse", "requested_scopes": ["view"]},
        )
        self.assertEqual(missing_key.status_code, 403, missing_key.get_json())

        anon_site = self.client.post(
            "/api/sites",
            json={"name": "Pop-up", "url": "https://example.com"},
        )
        self.assertEqual(anon_site.status_code, 401, anon_site.get_json())

        signup = self.client.post(
            "/api/auth/signup",
            json={"email": "new@example.com", "password": "secret12", "name": "New"},
        )
        self.assertEqual(signup.status_code, 200, signup.get_json())
        self.assertTrue(signup.get_json()["token"])

        duplicate = self.client.post(
            "/api/auth/signup",
            json={"email": "new@example.com", "password": "secret12", "name": "New"},
        )
        self.assertEqual(duplicate.status_code, 400, duplicate.get_json())
        self.assertIn("email", duplicate.get_json()["error"])
        _no_traceback(self, duplicate)

        empty = self.client.post("/api/auth/signup", json={})
        self.assertEqual(empty.status_code, 400, empty.get_json())
        self.assertIn("email and password", empty.get_json()["error"])

        owner = self._owner()
        created = self.client.post(
            "/api/sites",
            json={"name": "Pop-up", "url": "https://example.com"},
            headers={"X-Aurif-Owner": owner},
        )
        self.assertEqual(created.status_code, 200, created.get_json())
        self.assertEqual(created.get_json()["site"]["name"], "Pop-up")
        self.assertEqual(created.get_json()["site"]["url"], "https://example.com")

        defaulted = self.client.post(
            "/api/sites",
            json={},
            headers={"X-Aurif-Owner": owner},
        )
        self.assertEqual(defaulted.status_code, 200, defaulted.get_json())
        self.assertEqual(defaulted.get_json()["site"]["name"], "New site")

    def test_unexpected_exception_is_generic_500_without_traceback(self):
        with patch("store.create_user", side_effect=RuntimeError(_SENTINEL)):
            with self.assertLogs(app.logger, level="ERROR") as logs:
                response = self.client.post(
                    "/api/auth/signup",
                    json={"email": "boom@example.com", "password": "secret12", "name": "Boom"},
                )
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.get_json(), {"error": "internal server error"})
        _no_traceback(self, response)
        self.assertNotIn("RuntimeError", response.get_data(as_text=True))
        logged = "\n".join(logs.output)
        self.assertIn(_SENTINEL, logged)
        self.assertIn("Traceback", logged)

    def test_http_exceptions_keep_their_status(self):
        missing = self.client.get("/api/does-not-exist")
        self.assertEqual(missing.status_code, 404)
        self.assertNotIn("traceback", missing.get_data(as_text=True).lower())
        self.assertNotEqual((missing.get_json() or {}).get("error"), "internal server error")

        wrong_method = self.client.post("/")
        self.assertEqual(wrong_method.status_code, 405)
        self.assertNotIn("traceback", wrong_method.get_data(as_text=True).lower())
        self.assertNotEqual((wrong_method.get_json() or {}).get("error"), "internal server error")

        home = self.client.get("/")
        self.assertEqual(home.status_code, 200, home.get_json())
        self.assertTrue(home.get_json()["ok"])


if __name__ == "__main__":
    unittest.main()
