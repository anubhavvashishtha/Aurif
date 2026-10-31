"""Regression tests for enforcement bugs M1–M6. No network and no model keys."""

from __future__ import annotations

import base64
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER = Path(__file__).resolve().parents[1]
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

import human_gate  # noqa: E402
import store  # noqa: E402
from app import app, cart_by_session, sessions  # noqa: E402
from redact import redact_agent_payload  # noqa: E402

BROWSER = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}
LOW_RISK = {
    "risk": "low",
    "reason": "test",
    "suggested_scopes": ["view", "act"],
    "drop_act": False,
}
PRICE_KEYS = {"price", "compare_at", "discount"}


def _keys_named(value, names: set[str]) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in names:
                found.append(key)
            found.extend(_keys_named(child, names))
    elif isinstance(value, list):
        for child in value:
            found.extend(_keys_named(child, names))
    return found


class PathAndRedaction(unittest.TestCase):
    def test_canonical_path_collapses_the_reported_bypasses(self):
        self.assertEqual(store.canonical_ai_path("/products//field-tote"), "/products/field-tote")
        self.assertEqual(store.canonical_ai_path("/products/x/field-tote"), "/products/x/field-tote")
        self.assertEqual(store.classify_ai_path("/products/x/field-tote"), "unmapped")
        self.assertEqual(store.canonical_ai_path("/products/../cart"), "/cart")
        self.assertEqual(store.canonical_ai_path("/products/%2e%2e/cart"), "/cart")
        self.assertEqual(store.canonical_ai_path("/CART"), "/cart")
        self.assertEqual(store.canonical_ai_path("cart"), "/cart")
        self.assertEqual(store.canonical_ai_path("/products/Field-Tote/"), "/products/field-tote")
        self.assertEqual(store.product_slug("/products/x/field-tote"), None)
        self.assertEqual(store.product_slug("/products//field-tote"), "field-tote")

    def test_hidden_price_strips_compare_at_discount_and_element_meta(self):
        payload = {
            "meta": {"products": [{"name": "Field Tote", "price": 68, "rating": 4.7}]},
            "elements": [{"meta": {"price": 68, "compare_at": 85, "discount": 20, "rating": 4.7}}],
            "discount": 20,
            "rating": 4.7,
        }
        fields = [{"key": "meta.products[].price", "agent_visible": False}]
        out = redact_agent_payload(payload, fields)
        self.assertEqual(_keys_named(out, PRICE_KEYS), [])
        self.assertEqual(out["elements"][0]["meta"]["rating"], 4.7)
        self.assertEqual(out["meta"]["products"][0]["name"], "Field Tote")
        self.assertEqual(out["rating"], 4.7)


class EnforcementApi(unittest.TestCase):
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
        os.environ.pop("AURIF_ALLOW_HUMAN_BYPASS", None)
        sessions.clear()
        cart_by_session.clear()
        human_gate._challenges.clear()
        human_gate._human_sessions.clear()
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

    def _headers(self, session: str | None = None) -> dict[str, str]:
        headers = {"X-Aurif-Site-Key": self.site_key}
        if session:
            headers["X-Aurif-Session"] = session
        return headers

    def _handshake(self, agent_id: str = "qa", scopes: list[str] | None = None, purpose: str = "browse") -> dict:
        response = self.client.post(
            "/ai/handshake",
            json={
                "agent_id": agent_id,
                "requested_scopes": scopes or ["view"],
                "purpose": purpose,
            },
            headers=self._headers(),
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def _set_access(self, owner: str, endpoint_id: str, allowed: bool) -> None:
        response = self.client.put(
            f"/api/sites/demo-shop/endpoints/{endpoint_id}",
            json={"agent_access": allowed},
            headers={"X-Aurif-Owner": owner},
        )
        self.assertEqual(response.status_code, 200, response.get_json())

    def _hide(self, owner: str, endpoint_id: str, key: str) -> None:
        response = self.client.put(
            f"/api/sites/demo-shop/endpoints/{endpoint_id}",
            json={"response_fields": [{"key": key, "agent_visible": False}]},
            headers={"X-Aurif-Owner": owner},
        )
        self.assertEqual(response.status_code, 200, response.get_json())

    def _events(self) -> list[dict]:
        return store.activity_for_site("demo-shop", limit=50)

    def test_m1_noncanonical_product_paths_cannot_skip_a_closed_page(self):
        owner = self._owner()
        self._set_access(owner, "page.product", False)
        session = self._handshake()["session_token"]
        for path in ("/products/field-tote", "/products/x/field-tote", "/products//field-tote", "/products/field-tote/"):
            response = self.client.get("/ai/page", query_string={"path": path}, headers=self._headers(session))
            body = response.get_json()
            self.assertEqual(response.status_code, 403, body)
            self.assertTrue(body.get("blocked"))
            self.assertNotIn("NL-BG-001", json.dumps(body))
            self.assertEqual(_keys_named(body, PRICE_KEYS), [])

    def test_m1_open_page_still_redacts_the_canonical_double_slash_path(self):
        owner = self._owner()
        self._hide(owner, "page.product", "meta.price")
        session = self._handshake()["session_token"]
        response = self.client.get(
            "/ai/page",
            query_string={"path": "/products//field-tote"},
            headers=self._headers(session),
        )
        body = response.get_json()
        self.assertEqual(response.status_code, 200, body)
        self.assertEqual(body["path"], "/products/field-tote")
        self.assertEqual(body["meta"]["sku"], "NL-BG-001")
        self.assertEqual(_keys_named(body, PRICE_KEYS), [])
        self.assertNotIn("compare_at", json.dumps(body))

        leaked = self.client.get(
            "/ai/page",
            query_string={"path": "/products/x/field-tote"},
            headers=self._headers(session),
        )
        leaked_body = leaked.get_json()
        self.assertEqual(leaked.status_code, 403, leaked_body)
        self.assertNotIn("NL-BG-001", json.dumps(leaked_body))

    def test_m1_case_and_dot_segments_follow_the_closed_page(self):
        owner = self._owner()
        self._set_access(owner, "page.cart", False)
        session = self._handshake()["session_token"]
        for path in ("/cart", "/cart/", "cart", "/CART", "/products/../cart", "/products/%2e%2e/cart"):
            response = self.client.get("/ai/page", query_string={"path": path}, headers=self._headers(session))
            self.assertEqual(response.status_code, 403, response.get_json())

    def test_m2_bypass_token_is_rejected_unless_the_dev_flag_is_on(self):
        header = {**BROWSER, "X-Aurif-Human": "bypass"}
        products = self.client.get("/api/products", headers=header)
        self.assertEqual(products.status_code, 401, products.get_json())
        self.assertEqual(products.get_json()["error"], "human_captcha_required")

        self.client.set_cookie("aurif_human", "bypass")
        cooked = self.client.get("/api/products", headers=BROWSER)
        self.assertEqual(cooked.status_code, 401, cooked.get_json())

        check = self.client.get("/api/public/human-check", headers={"X-Aurif-Human": "bypass"})
        self.assertFalse(check.get_json()["ok"])

        os.environ["AURIF_ALLOW_HUMAN_BYPASS"] = "0"
        still_off = self.client.get("/api/public/human-check", headers={"X-Aurif-Human": "bypass"})
        self.assertFalse(still_off.get_json()["ok"])

        os.environ["AURIF_ALLOW_HUMAN_BYPASS"] = "1"
        allowed = self.client.get("/api/products", headers=header)
        self.assertEqual(allowed.status_code, 200, allowed.get_json())
        self.assertTrue(self.client.get("/api/public/human-check", headers={"X-Aurif-Human": "bypass"}).get_json()["ok"])

    def test_m2_captcha_off_issues_a_real_token_that_bypass_does_not_replace(self):
        owner = self._owner()
        off = self.client.patch(
            "/api/sites/demo-shop",
            json={"require_human_captcha": False},
            headers={"X-Aurif-Owner": owner},
        )
        self.assertEqual(off.status_code, 200, off.get_json())
        issued = self.client.post("/api/public/human-verify", json={})
        self.assertEqual(issued.status_code, 200, issued.get_json())
        token = issued.get_json()["human_token"]
        self.assertNotEqual(token, "bypass")
        self.assertTrue(human_gate.human_session_valid(token))

        on = self.client.patch(
            "/api/sites/demo-shop",
            json={"require_human_captcha": True},
            headers={"X-Aurif-Owner": owner},
        )
        self.assertEqual(on.status_code, 200, on.get_json())
        real = self.client.get("/api/products", headers={**BROWSER, "X-Aurif-Human": token})
        self.assertEqual(real.status_code, 200, real.get_json())
        forged = self.client.get("/api/products", headers={**BROWSER, "X-Aurif-Human": "bypass"})
        self.assertEqual(forged.status_code, 401, forged.get_json())

    def test_m3_hidden_price_is_absent_from_shop_elements_product_and_add(self):
        owner = self._owner()
        self._hide(owner, "page.products", "meta.products[].price")
        self._hide(owner, "page.product", "meta.price")
        self._hide(owner, "page.cart", "meta.products[].price")
        session = self._handshake(scopes=["view", "act"])["session_token"]

        shop = self.client.get("/ai/page", query_string={"path": "/products"}, headers=self._headers(session))
        shop_body = shop.get_json()
        self.assertEqual(shop.status_code, 200, shop_body)
        self.assertEqual(_keys_named(shop_body, PRICE_KEYS), [])
        self.assertGreater(len(shop_body["elements"]), 1)
        self.assertIn("rating", json.dumps(shop_body["elements"]))

        product = self.client.get(
            "/ai/page",
            query_string={"path": "/products/field-tote"},
            headers=self._headers(session),
        )
        product_body = product.get_json()
        self.assertEqual(product.status_code, 200, product_body)
        self.assertEqual(_keys_named(product_body, PRICE_KEYS), [])
        self.assertEqual(product_body["meta"]["sku"], "NL-BG-001")
        self.assertEqual(product_body["rating"], 4.7)
        self.assertNotIn("85", json.dumps(product_body))

        added = self.client.post(
            "/ai/actions",
            json={"action_id": "product.add:field-tote"},
            headers=self._headers(session),
        )
        added_body = added.get_json()
        self.assertEqual(added.status_code, 200, added_body)
        self.assertEqual(added_body["result"]["added"]["slug"], "field-tote")
        self.assertEqual(added_body["result"]["added"]["name"], "Field Tote")
        self.assertEqual(_keys_named(added_body, PRICE_KEYS), [])
        self.assertNotIn("description", added_body["result"]["added"])

    def test_m3_visible_price_is_still_returned(self):
        session = self._handshake()["session_token"]
        response = self.client.get(
            "/ai/page",
            query_string={"path": "/products/field-tote"},
            headers=self._headers(session),
        )
        body = response.get_json()
        self.assertEqual(response.status_code, 200, body)
        self.assertEqual(body["meta"]["price"], 68)
        self.assertEqual(body["meta"]["compare_at"], 85)
        self.assertEqual(body["discount"], 20)

    def test_m4_denials_are_logged_and_closed_navigation_is_not_a_success(self):
        session = self._handshake(scopes=["view"])["session_token"]

        missing = self.client.get("/ai/page", query_string={"path": "/products"}, headers=self._headers())
        self.assertEqual(missing.status_code, 401, missing.get_json())
        self.assertEqual(self._events()[0]["kind"], "page_blocked")
        self.assertEqual(self._events()[0]["detail"]["reason"], "no_session")
        self.assertFalse(self._events()[0]["detail"]["accepted"])

        sessions[session]["expires_at"] = time.time() - 5
        expired = self.client.get("/ai/page", query_string={"path": "/"}, headers=self._headers(session))
        self.assertEqual(expired.status_code, 401, expired.get_json())
        self.assertEqual(self._events()[0]["detail"]["reason"], "no_session")
        fresh = self._handshake(scopes=["view"])["session_token"]

        denied = self.client.post(
            "/ai/actions",
            json={"action_id": "product.add:field-tote"},
            headers=self._headers(fresh),
        )
        self.assertEqual(denied.status_code, 403, denied.get_json())
        self.assertIn("act", denied.get_json()["error"])
        self.assertEqual(self._events()[0]["kind"], "action_blocked")
        self.assertEqual(self._events()[0]["detail"]["reason"], "scope_not_granted")

        unknown = self.client.post(
            "/ai/actions",
            json={"action_id": "admin.drop"},
            headers=self._headers(fresh),
        )
        self.assertEqual(unknown.status_code, 404, unknown.get_json())
        self.assertEqual(self._events()[0]["kind"], "action_blocked")
        self.assertEqual(self._events()[0]["detail"]["reason"], "unknown_action")

        owner = self._owner()
        self._set_access(owner, "page.cart", False)
        self._set_access(owner, "page.product", False)
        nav = self.client.post(
            "/ai/actions",
            json={"action_id": "nav.cart"},
            headers=self._headers(fresh),
        )
        nav_body = nav.get_json()
        self.assertEqual(nav.status_code, 403, nav_body)
        self.assertFalse(nav_body["ok"])
        self.assertTrue(nav_body["page"]["blocked"])
        self.assertEqual(self._events()[0]["kind"], "page_blocked")
        self.assertFalse(self._events()[0]["detail"]["accepted"])
        self.assertFalse(any(e["kind"] == "action" and e.get("action_id") == "nav.cart" and e["detail"].get("accepted") for e in self._events()))

        view = self.client.post(
            "/ai/actions",
            json={"action_id": "product.view:field-tote"},
            headers=self._headers(fresh),
        )
        self.assertEqual(view.status_code, 403, view.get_json())
        self.assertEqual(self._events()[0]["kind"], "page_blocked")
        self.assertFalse(self._events()[0]["detail"]["accepted"])

    def test_m5_audit_requires_a_session_and_returns_only_that_session(self):
        open_audit = self.client.get("/ai/audit", headers=self._headers())
        self.assertEqual(open_audit.status_code, 401, open_audit.get_json())
        self.assertNotIn("events", open_audit.get_json())

        agent_a = self._handshake(agent_id="qa", purpose="agent-a-browse-purpose")
        agent_b = self._handshake(agent_id="qa-view", purpose="agent-b-secret-purpose")
        self.client.get("/ai/page", query_string={"path": "/"}, headers=self._headers(agent_a["session_token"]))
        self.client.get("/ai/page", query_string={"path": "/products"}, headers=self._headers(agent_b["session_token"]))

        own = self.client.get("/ai/audit", headers=self._headers(agent_a["session_token"]))
        self.assertEqual(own.status_code, 200, own.get_json())
        dumped = json.dumps(own.get_json())
        self.assertIn("agent-a-browse-purpose", dumped)
        self.assertNotIn("agent-b-secret-purpose", dumped)
        self.assertTrue(own.get_json()["events"])

        owner = self._owner()
        full = self.client.get("/api/sites/demo-shop/activity", headers={"X-Aurif-Owner": owner})
        self.assertEqual(full.status_code, 200, full.get_json())
        full_dump = json.dumps(full.get_json())
        self.assertIn("agent-a-browse-purpose", full_dump)
        self.assertIn("agent-b-secret-purpose", full_dump)

    def test_m6_challenge_hides_the_answer_and_locks_after_one_redraw(self):
        issued = self.client.get("/api/public/human-challenge")
        body = issued.get_json()
        self.assertEqual(issued.status_code, 200, body)
        self.assertNotIn("target", body)
        row = human_gate.peek_challenge(body["challenge_id"])
        self.assertIsNotNone(row)
        target = row["target"]
        public = {key: value for key, value in body.items() if key != "image"}
        self.assertNotIn(target, json.dumps(public))
        self.assertTrue(body["image"].startswith("data:image/png;base64,"))
        png = base64.b64decode(body["image"].split(",", 1)[1])
        self.assertTrue(png.startswith(b"\x89PNG"))

        drawing = {"challenge_id": body["challenge_id"], "image": "data:image/png;base64,aaaa"}
        with patch("muse_client.verify_drawing", return_value={"ok": False, "reason": "drawing did not match"}):
            first = self.client.post("/api/public/human-verify", json=drawing)
            self.assertEqual(first.status_code, 403, first.get_json())
            self.assertIsNotNone(human_gate.peek_challenge(body["challenge_id"]))
            second = self.client.post("/api/public/human-verify", json=drawing)
            self.assertEqual(second.status_code, 403, second.get_json())
            self.assertIn("too many attempts", second.get_json()["error"])
            self.assertIsNone(human_gate.peek_challenge(body["challenge_id"]))
            third = self.client.post("/api/public/human-verify", json=drawing)
        self.assertEqual(third.status_code, 403, third.get_json())
        self.assertIn("expired", third.get_json()["error"])

    def test_m6_vision_outage_does_not_burn_the_challenge(self):
        issued = self.client.get("/api/public/human-challenge").get_json()
        with patch(
            "muse_client.verify_drawing",
            return_value={"ok": False, "reason": "vision provider misconfigured: test"},
        ):
            response = self.client.post(
                "/api/public/human-verify",
                json={"challenge_id": issued["challenge_id"], "image": "data:image/png;base64,aaaa"},
            )
        self.assertEqual(response.status_code, 502, response.get_json())
        self.assertIsNotNone(human_gate.peek_challenge(issued["challenge_id"]))
        self.assertEqual(human_gate.peek_challenge(issued["challenge_id"])["attempts"], 0)


if __name__ == "__main__":
    unittest.main()
