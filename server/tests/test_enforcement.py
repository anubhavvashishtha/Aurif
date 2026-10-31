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
from endpoints_default import ensure_endpoint_shape  # noqa: E402
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


def _string_values(value) -> list[str]:
    found: list[str] = []
    if isinstance(value, str):
        found.append(value)
    elif isinstance(value, dict):
        for child in value.values():
            found.extend(_string_values(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_string_values(child))
    return found


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
    def test_canonical_path_matches_configured_page_patterns(self):
        self.assertEqual(store.canonical_ai_path("/products//field-tote"), "/products/field-tote")
        self.assertEqual(store.canonical_ai_path("/products/x/field-tote"), "/products/x/field-tote")
        self.assertEqual(store.canonical_ai_path("/products/../cart"), "/cart")
        self.assertEqual(store.canonical_ai_path("/products/%2e%2e/cart"), "/cart")
        self.assertEqual(store.canonical_ai_path("/CART"), "/cart")
        self.assertEqual(store.canonical_ai_path("cart"), "/cart")
        self.assertEqual(store.canonical_ai_path("/products/Field-Tote/"), "/products/field-tote")
        site = {
            "endpoints": [
                {"id": "page.home", "kind": "page", "path": "/", "agent_access": True},
                {"id": "page.products", "kind": "page", "path": "/products", "agent_access": True},
                {"id": "page.product", "kind": "page", "path": "/products/*", "agent_access": True},
                {"id": "page.cart", "kind": "page", "path": "/cart", "agent_access": False},
                {"id": "page.about", "kind": "page", "path": "/About", "agent_access": True},
                {"id": "page.stories", "kind": "page", "path": "/stories/*", "agent_access": True},
            ]
        }
        self.assertEqual(store.page_decision(site, "/products/x/field-tote")[1], "unmapped")
        self.assertEqual(store.page_decision(site, "/products//field-tote"), ("/products/field-tote", "allow"))
        self.assertEqual(store.page_decision(site, "/CART")[1], "closed")
        self.assertEqual(store.page_decision(site, "/about")[1], "allow")
        self.assertEqual(store.page_decision(site, "/stories/portland"), ("/stories/portland", "allow"))
        self.assertEqual(store.page_decision(site, "/stories/a/b")[1], "unmapped")
        self.assertEqual(store.page_decision(site, "/shop")[1], "unmapped")
        self.assertEqual(store.capture_wildcard("/products/*", "/products//field-tote"), "field-tote")
        self.assertIsNone(store.capture_wildcard("/products/*", "/products/x/field-tote"))

    def test_custom_page_survives_schema_upgrade(self):
        upgraded = ensure_endpoint_shape(
            [
                {
                    "id": "page.about",
                    "kind": "page",
                    "path": "/about",
                    "agent_access": False,
                    "response_fields": [],
                },
                {
                    "id": "page.product.field-tote",
                    "kind": "page",
                    "path": "/products/field-tote",
                    "agent_access": False,
                    "response_fields": [],
                },
            ]
        )
        ids = {row["id"] for row in upgraded}
        self.assertIn("page.about", ids)
        self.assertIn("page.home", ids)
        self.assertNotIn("page.product.field-tote", ids)
        about = next(row for row in upgraded if row["id"] == "page.about")
        self.assertFalse(about["agent_access"])
        self.assertEqual(about["path"], "/about")

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

    def _add_page(self, endpoint: dict) -> None:
        def mut(data: dict) -> None:
            data["sites"]["demo-shop"]["endpoints"].append(endpoint)

        store.save(mut)

    def test_m1_owner_configured_page_outside_the_demo_routes(self):
        """Access follows the site's page endpoints, not a hardcoded path list."""
        session = self._handshake()["session_token"]
        headers = self._headers(session)
        for path in ("/", "/products", "/products/field-tote", "/cart"):
            response = self.client.get("/ai/page", query_string={"path": path}, headers=headers)
            body = response.get_json()
            self.assertEqual(response.status_code, 200, body)
            self.assertFalse(body.get("blocked"))
            self.assertEqual(body["path"], store.canonical_ai_path(path))

        # Storefront routes that have no agent endpoint stay denied.
        for path in ("/shop", "/about", "/bags", "/notebooks", "/tools", "/contact", "/shipping", "/checkout"):
            response = self.client.get("/ai/page", query_string={"path": path}, headers=headers)
            body = response.get_json()
            self.assertEqual(response.status_code, 403, body)
            self.assertTrue(body.get("blocked"))

        self._add_page(
            {
                "id": "page.about",
                "label": "About",
                "kind": "page",
                "path": "/about",
                "ref": "/about",
                "agent_access": True,
                "direction": "read",
                "response_fields": [
                    {"key": "title", "label": "title", "type": "string", "agent_visible": True},
                    {"key": "summary", "label": "summary", "type": "string", "agent_visible": True},
                    {"key": "meta.blurb", "label": "blurb", "type": "string", "agent_visible": False},
                ],
                "request_fields": [],
                "sample_response": {
                    "title": "Our story",
                    "summary": "Made in Portland.",
                    "elements": [],
                    "meta": {"blurb": "workshop notes"},
                },
                "sample_request": {},
            }
        )
        self._add_page(
            {
                "id": "page.stories",
                "label": "Stories",
                "kind": "page",
                "path": "/stories/*",
                "ref": "/stories/*",
                "agent_access": True,
                "direction": "read",
                "response_fields": [{"key": "title", "label": "title", "type": "string", "agent_visible": True}],
                "request_fields": [],
                "sample_response": {"title": "Field notes", "summary": "A configured wildcard page.", "elements": [], "meta": {}},
                "sample_request": {},
            }
        )

        about = self.client.get("/ai/page", query_string={"path": "/ABOUT/"}, headers=headers)
        about_body = about.get_json()
        self.assertEqual(about.status_code, 200, about_body)
        self.assertFalse(about_body.get("blocked"))
        self.assertEqual(about_body["path"], "/about")
        self.assertEqual(about_body["title"], "Our story")
        self.assertNotIn("blurb", json.dumps(about_body))
        self.assertNotIn("workshop notes", json.dumps(about_body))

        story = self.client.get("/ai/page", query_string={"path": "/stories//portland"}, headers=headers)
        story_body = story.get_json()
        self.assertEqual(story.status_code, 200, story_body)
        self.assertEqual(story_body["path"], "/stories/portland")
        self.assertEqual(story_body["title"], "Field notes")
        nested = self.client.get("/ai/page", query_string={"path": "/stories/a/b"}, headers=headers)
        self.assertEqual(nested.status_code, 403, nested.get_json())

        owner = self._owner()
        self._set_access(owner, "page.about", False)
        self._set_access(owner, "page.stories", False)
        closed = self.client.get("/ai/page", query_string={"path": "/about"}, headers=headers)
        closed_body = closed.get_json()
        self.assertEqual(closed.status_code, 403, closed_body)
        self.assertTrue(closed_body.get("blocked"))
        self.assertNotIn("Our story", json.dumps(closed_body))
        self.assertNotIn("workshop notes", json.dumps(closed_body))
        closed_story = self.client.get("/ai/page", query_string={"path": "/stories/portland"}, headers=headers)
        self.assertEqual(closed_story.status_code, 403, closed_story.get_json())

        # The same owner toggle still controls the original shop page.
        self._set_access(owner, "page.products", False)
        shop = self.client.get("/ai/page", query_string={"path": "/products"}, headers=headers)
        self.assertEqual(shop.status_code, 403, shop.get_json())

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

    def _field_visible(self, site: dict, endpoint_id: str, key: str) -> bool:
        endpoint = next(row for row in site["endpoints"] if row["id"] == endpoint_id)
        field = next(row for row in endpoint["response_fields"] if row["key"] == key)
        return bool(field["agent_visible"])

    def test_p10_price_toggle_is_sitewide_on_every_page(self):
        owner = self._owner()
        self._hide(owner, "page.product", "meta.price")
        site = self.client.get("/api/sites/demo-shop", headers={"X-Aurif-Owner": owner}).get_json()["site"]
        for endpoint_id, key in (
            ("page.product", "meta.price"),
            ("page.products", "meta.products[].price"),
            ("page.products", "elements[].meta.price"),
            ("page.cart", "meta.products[].price"),
        ):
            self.assertFalse(self._field_visible(site, endpoint_id, key), f"{endpoint_id} {key}")
        self.assertTrue(self._field_visible(site, "page.product", "meta.sku"))
        self.assertTrue(self._field_visible(site, "page.products", "meta.products[].rating"))

        shown = self.client.put(
            "/api/sites/demo-shop/endpoints/page.cart",
            json={"response_fields": [{"key": "meta.products[].price", "agent_visible": True}]},
            headers={"X-Aurif-Owner": owner},
        )
        self.assertEqual(shown.status_code, 200, shown.get_json())
        restored = shown.get_json()["site"]
        for endpoint_id, key in (
            ("page.product", "meta.price"),
            ("page.products", "meta.products[].price"),
            ("page.products", "elements[].meta.price"),
            ("page.cart", "meta.products[].price"),
        ):
            self.assertTrue(self._field_visible(restored, endpoint_id, key), f"{endpoint_id} {key}")

    def test_n7_price_hidden_on_the_product_page_is_withheld_from_the_shop_list(self):
        owner = self._owner()
        session = self._handshake(scopes=["view", "act"])["session_token"]
        headers = self._headers(session)

        before = self.client.get("/ai/page", query_string={"path": "/products"}, headers=headers)
        before_body = before.get_json()
        self.assertEqual(before.status_code, 200, before_body)
        self.assertIn("price", json.dumps(before_body))
        self.assertEqual(before_body["meta"]["products"][0]["price"], 68)

        self._hide(owner, "page.product", "meta.price")

        shop = self.client.get("/ai/page", query_string={"path": "/products"}, headers=headers)
        shop_body = shop.get_json()
        self.assertEqual(shop.status_code, 200, shop_body)
        self.assertEqual(_keys_named(shop_body, PRICE_KEYS), [])
        self.assertNotIn("68", json.dumps(shop_body))
        self.assertNotIn("85", json.dumps(shop_body))
        self.assertIn("Field Tote", json.dumps(shop_body))
        self.assertIn("rating", json.dumps(shop_body["elements"]))

        product = self.client.get(
            "/ai/page",
            query_string={"path": "/products/field-tote"},
            headers=headers,
        )
        product_body = product.get_json()
        self.assertEqual(product.status_code, 200, product_body)
        self.assertEqual(_keys_named(product_body, PRICE_KEYS), [])
        self.assertEqual(product_body["meta"]["sku"], "NL-BG-001")
        self.assertEqual(product_body["rating"], 4.7)

        added = self.client.post(
            "/ai/actions",
            json={"action_id": "product.add:field-tote"},
            headers=headers,
        )
        added_body = added.get_json()
        self.assertEqual(added.status_code, 200, added_body)
        self.assertEqual(_keys_named(added_body, PRICE_KEYS), [])

        cart = self.client.get("/ai/page", query_string={"path": "/cart"}, headers=headers)
        cart_body = cart.get_json()
        self.assertEqual(cart.status_code, 200, cart_body)
        self.assertEqual(_keys_named(cart_body, PRICE_KEYS), [])
        self.assertIn("Field Tote", json.dumps(cart_body))

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
        # A one-letter answer can occur inside unrelated copy ("Aurif", "AI").
        # Reject it as its own value, and reject longer answers anywhere in the copy.
        values = list(_string_values(public))
        self.assertNotIn(target, values)
        if len(target) > 1:
            self.assertFalse(any(target in text for text in values))
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
