"""Muse browse blockers B1–B3, with mocked model responses and no API key.

The integration cases boot the Flask app on an ephemeral port and point Muse at
it, so handshake scope checks and /ai/actions denials are the real gate.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

SERVER = Path(__file__).resolve().parents[1]
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

import muse_browse  # noqa: E402
import store  # noqa: E402
from app import app, cart_by_session, sessions  # noqa: E402

ENV_KEYS = (
    "META_API_KEY",
    "MODEL_API_KEY",
    "META_BASE_URL",
    "META_MODEL",
    "META_PROVIDER",
    "META_VISION_API_KEY",
    "META_VISION_BASE_URL",
    "META_VISION_MODEL",
    "META_VISION_PROVIDER",
    "META_REASONING_EFFORT",
    "BASETEN_API_KEY",
    "BASETEN_MODEL",
    "MODAL_VISION_MODEL",
    "MODAL_BASE_URL",
    "MODAL_TOKEN_ID",
    "MODAL_TOKEN_SECRET",
)

LOW_RISK = {
    "risk": "low",
    "reason": "shopper help",
    "suggested_scopes": ["view", "act"],
    "drop_act": False,
}
DROP_ACT = {
    "risk": "high",
    "reason": "automated cart mutation",
    "suggested_scopes": ["view"],
    "drop_act": True,
}
HOSTILE_PRICE = "The price of Field Tote is 85."


class _ScriptedModel:
    """OpenAI stand-in. Routes by prompt so risk, vision, and phrasing differ."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.risk = dict(LOW_RISK)
        self.answer = HOSTILE_PRICE
        self.vision = {
            "match": False,
            "human_like": False,
            "read_as": "",
            "reason": "bot drawing",
        }

    def reset(self, *, risk: dict | None = None, answer: str = HOSTILE_PRICE) -> None:
        self.calls.clear()
        self.risk = dict(risk or LOW_RISK)
        self.answer = answer

    def client(self, **kwargs):
        script = self

        class _Completions:
            def create(_self, **call):
                script.calls.append(call)
                blob = json.dumps(call.get("messages"), default=str)
                if "CAPTCHA check" in blob or "image_url" in blob:
                    content = json.dumps(script.vision)
                elif "handshake risk classifier" in blob:
                    content = json.dumps(script.risk)
                else:
                    content = script.answer
                msg = MagicMock()
                msg.content = content
                msg.reasoning_content = None
                choice = MagicMock()
                choice.message = msg
                resp = MagicMock()
                resp.choices = [choice]
                return resp

        class _Chat:
            def __init__(_self):
                _self.completions = _Completions()

        class _Client:
            def __init__(_self, **_kwargs):
                _self.chat = _Chat()

        return _Client(**kwargs)

    def answer_prompts(self) -> list[str]:
        prompts = []
        for call in self.calls:
            blob = json.dumps(call.get("messages"), default=str)
            if "Answer the user in ONE short sentence" in blob:
                prompts.append(blob)
        return prompts


def _products() -> dict:
    return {"field-tote": {"name": "Field Tote", "slug": "field-tote"}}


class MusePathAndPrice(unittest.TestCase):
    def test_shop_and_product_language_resolves_to_products(self):
        products = _products()
        for message in (
            "open the shop",
            "show me the products",
            "product",
            "browse the catalog",
            "open https://northline.example/shop",
            "go to /shop",
        ):
            self.assertEqual(
                muse_browse.shop_path_from_message(message, products),
                "/products",
                message,
            )
        self.assertEqual(muse_browse.shop_path_from_message("open the cart", products), "/cart")
        self.assertEqual(
            muse_browse.shop_path_from_message("what is the price of the field tote", products),
            "/products/field-tote",
        )

    def test_add_intent_requests_act_and_view_questions_do_not(self):
        products = _products()
        self.assertEqual(
            muse_browse.action_from_message("add the Field Tote to my cart", products),
            {"action_id": "product.add:field-tote", "kind": "add", "slug": "field-tote"},
        )
        self.assertIsNone(muse_browse.action_from_message("what is the price of the field tote", products))
        self.assertIsNone(muse_browse.action_from_message("open the shop", products))
        self.assertIsNone(muse_browse.action_from_message("show me the products", products))

    def test_hidden_price_is_not_replaced_by_compare_at_or_the_model(self):
        fields = [
            {"label": "Name", "value": "Field Tote"},
            {"label": "Compare at", "value": "85"},
            {"label": "Rating", "value": "4.7"},
        ]
        with patch("muse_browse.muse_client.complete", return_value=HOSTILE_PRICE) as complete:
            reply = muse_browse._compose_reply(
                message="what is the price of the field tote",
                steps=[],
                fields=fields,
                denied=False,
            )
        self.assertEqual(complete.call_count, 0)
        self.assertIn("isn't shared", reply)
        self.assertNotIn("85", reply)
        self.assertNotIn("68", reply)

    def test_model_cannot_substitute_compare_at_when_price_is_present(self):
        fields = [
            {"label": "Name", "value": "Field Tote"},
            {"label": "Price", "value": "68"},
            {"label": "Compare at", "value": "85"},
        ]
        with patch("muse_browse.muse_client.complete", return_value=HOSTILE_PRICE) as complete:
            reply = muse_browse._compose_reply(
                message="what is the price of the field tote",
                steps=[],
                fields=fields,
                denied=False,
            )
        self.assertEqual(complete.call_count, 1)
        prompt = complete.call_args.args[0][0]["content"]
        self.assertNotIn("85", prompt)
        self.assertIn("68", prompt)
        self.assertIn("68", reply)
        self.assertNotIn("85", reply)

    def test_action_denial_is_quoted_and_not_rewritten(self):
        with patch("muse_browse.muse_client.complete", return_value="Field Tote is in the cart.") as complete:
            blocked = muse_browse._compose_reply(
                message="add the Field Tote to my cart",
                steps=[],
                fields=[{"label": "Name", "value": "Field Tote"}, {"label": "Compare at", "value": "85"}],
                denied=True,
                action_outcome={
                    "ok": False,
                    "action_id": "product.add:field-tote",
                    "error": "action blocked for AI agents by site owner",
                },
            )
            missing_scope = muse_browse._compose_reply(
                message="add the Field Tote to my cart",
                steps=[],
                fields=[],
                denied=True,
                action_outcome={
                    "ok": False,
                    "action_id": "product.add:field-tote",
                    "error": "scope 'act' not granted",
                },
            )
        self.assertEqual(complete.call_count, 0)
        self.assertIn("action blocked", blocked)
        self.assertNotIn("in the cart", blocked)
        self.assertIn("scope 'act' not granted", missing_scope)


class MuseBrowseRepros(unittest.TestCase):
    """QA repros against the live permission gate. Model calls are scripted."""

    script = _ScriptedModel()

    @classmethod
    def setUpClass(cls):
        cls._saved_env = {key: os.environ.get(key) for key in ENV_KEYS}
        cls._dotenv = patch("muse_client.load_dotenv", lambda *args, **kwargs: False)
        cls._dotenv.start()
        for key in ENV_KEYS:
            os.environ.pop(key, None)
        os.environ["META_API_KEY"] = "test-meta-key"
        os.environ["META_BASE_URL"] = "https://api.meta.ai/v1"
        os.environ["META_MODEL"] = "muse-spark-1.3"
        os.environ["META_PROVIDER"] = "meta"

        cls._tmp = tempfile.TemporaryDirectory()
        cls._store = patch.object(store, "STORE_PATH", Path(cls._tmp.name) / "store.json")
        cls._store.start()
        sessions.clear()
        cart_by_session.clear()

        cls._openai = patch("muse_client.OpenAI", cls.script.client)
        cls._openai.start()

        from werkzeug.serving import make_server

        cls._httpd = make_server("127.0.0.1", 0, app, threaded=True)
        cls._thread = threading.Thread(target=cls._httpd.serve_forever, daemon=True)
        cls._thread.start()
        # Muse calls the API through config.api_public_url(); point that at this process.
        cls._saved_public_url = os.environ.get("AURIF_API_PUBLIC_URL")
        os.environ["AURIF_API_PUBLIC_URL"] = f"http://127.0.0.1:{cls._httpd.server_port}"

        cls.client = app.test_client()
        login = cls.client.post(
            "/api/auth/login",
            json={"email": "owner@aurif.dev", "password": "demo1234"},
        )
        assert login.status_code == 200, login.get_data(as_text=True)
        token = login.get_json()["token"]
        cls.owner = {"X-Aurif-Owner": token}
        me = cls.client.get("/api/auth/me", headers=cls.owner)
        assert me.status_code == 200, me.get_data(as_text=True)
        cls.site_key = me.get_json()["sites"][0]["site_key"]

    @classmethod
    def tearDownClass(cls):
        if cls._saved_public_url is None:
            os.environ.pop("AURIF_API_PUBLIC_URL", None)
        else:
            os.environ["AURIF_API_PUBLIC_URL"] = cls._saved_public_url
        cls._httpd.shutdown()
        cls._thread.join(timeout=5)
        cls._httpd.server_close()
        cls._openai.stop()
        cls._store.stop()
        cls._dotenv.stop()
        cls._tmp.cleanup()
        for key, value in cls._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def setUp(self):
        self.script.reset()
        sessions.clear()
        cart_by_session.clear()

    def _events(self) -> list[dict]:
        response = self.client.get("/api/sites/demo-shop/activity", headers=self.owner)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.get_json()["events"]

    def _chat(self, message: str, *, use_site_key: bool = True) -> dict:
        response = self.client.post(
            "/api/ai/agent-chat",
            json={
                "message": message,
                "use_site_key": use_site_key,
                "site_key": self.site_key if use_site_key else "",
            },
            headers=self.owner,
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.get_json()

    def _fresh(self, message: str, **kwargs) -> tuple[dict, list[dict]]:
        before = {event["id"] for event in self._events()}
        body = self._chat(message, **kwargs)
        fresh = [event for event in self._events() if event["id"] not in before]
        return body, fresh

    def _set_price_visible(self, visible: bool) -> None:
        response = self.client.put(
            "/api/sites/demo-shop/endpoints/page.product",
            json={"response_fields": [{"key": "meta.price", "agent_visible": visible}]},
            headers=self.owner,
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))

    def _set_add_allowed(self, allowed: bool) -> None:
        response = self.client.put(
            "/api/sites/demo-shop/endpoints/action.product.add",
            json={"agent_access": allowed},
            headers=self.owner,
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))

    def test_b1_add_field_tote_requests_act_and_posts_action(self):
        body, fresh = self._fresh("add the Field Tote to my cart")
        self.assertFalse(body["denied"])
        self.assertIn("Field Tote", body["reply"])
        self.assertIn("cart", body["reply"].lower())
        self.assertNotIn("85", body["reply"])

        action_steps = [
            step
            for step in body["steps"]
            if step.get("method") == "POST" and str(step.get("url", "")).rstrip("/").endswith("/ai/actions")
        ]
        self.assertEqual(len(action_steps), 1)
        self.assertEqual(action_steps[0].get("action_id"), "product.add:field-tote")
        self.assertEqual(action_steps[0]["result"], "ok")

        handshakes = [event for event in fresh if event["kind"] == "handshake"]
        self.assertTrue(handshakes)
        self.assertEqual(handshakes[0]["detail"]["asked"]["requested_scopes"], ["view", "act"])
        self.assertIn("act", handshakes[0]["detail"]["granted_scopes"])

        actions = [event for event in fresh if event["kind"] == "action"]
        self.assertTrue(actions)
        self.assertEqual(actions[0]["action_id"], "product.add:field-tote")
        self.assertTrue(actions[0]["detail"]["accepted"])

        findings = [
            item
            for item in body["site_response"]["findings"]
            if str(item.get("url", "")).rstrip("/").endswith("/ai/actions")
        ]
        self.assertIn("field-tote", findings[-1]["json"]["result"]["cart"])

    def test_b1_scope_denial_is_explained(self):
        self.script.reset(risk=DROP_ACT)
        body, fresh = self._fresh("add the Field Tote to my cart")
        self.assertTrue(body["denied"])
        self.assertIn("scope 'act' not granted", body["reply"])
        self.assertNotIn("in the cart", body["reply"])
        handshakes = [event for event in fresh if event["kind"] == "handshake"]
        self.assertEqual(handshakes[0]["detail"]["asked"]["requested_scopes"], ["view", "act"])
        self.assertNotIn("act", handshakes[0]["detail"]["granted_scopes"])
        self.assertFalse(any(event["kind"] == "action" and event["detail"].get("accepted") for event in fresh))

    def test_b1_owner_block_is_explained(self):
        self._set_add_allowed(False)
        try:
            body, fresh = self._fresh("buy the field tote")
        finally:
            self._set_add_allowed(True)
        self.assertTrue(body["denied"])
        self.assertIn("action blocked", body["reply"])
        self.assertNotIn("in the cart", body["reply"])
        blocked = [event for event in fresh if event["kind"] == "action_blocked"]
        self.assertTrue(blocked)
        self.assertEqual(blocked[0]["action_id"], "product.add:field-tote")
        self.assertFalse(blocked[0]["detail"]["accepted"])

    def test_b1_view_question_does_not_request_act(self):
        body, fresh = self._fresh("what is the rating of the field tote")
        self.assertNotIn("/ai/actions", " ".join(str(step.get("url", "")) for step in body["steps"]))
        self.assertIn("4.7", body["reply"])
        self.assertNotIn("85", body["reply"])
        handshakes = [event for event in fresh if event["kind"] == "handshake"]
        self.assertEqual(handshakes[0]["detail"]["asked"]["requested_scopes"], ["view"])
        self.assertFalse(any(event["kind"] == "action" for event in fresh))

    def test_b2_hidden_price_is_not_answered_with_compare_at(self):
        self._set_price_visible(False)
        try:
            body, _fresh = self._fresh("what is the price of the field tote")
        finally:
            self._set_price_visible(True)

        pages = [
            item
            for item in body["site_response"]["findings"]
            if isinstance(item.get("json"), dict) and item["json"].get("path") == "/products/field-tote"
        ]
        self.assertTrue(pages)
        meta = pages[-1]["json"]["meta"]
        self.assertNotIn("price", meta)
        self.assertNotIn("compare_at", meta)

        self.assertIn("isn't shared", body["reply"])
        self.assertNotIn("85", body["reply"])
        self.assertNotIn("68", body["reply"])
        self.assertEqual(self.script.answer_prompts(), [])

    def test_b3_shop_and_product_open_the_catalog(self):
        for message in ("open the shop", "show me the products"):
            self.script.reset()
            body, fresh = self._fresh(message)
            self.assertEqual(body["path"], "/products", message)
            self.assertNotIn("/shop", body["url"])
            self.assertTrue(body["url"].endswith("/products"), body["url"])
            self.assertIn("Field Tote", body["reply"])
            page_urls = [
                str(step.get("url", ""))
                for step in body["steps"]
                if "/ai/page" in str(step.get("url", ""))
            ]
            self.assertTrue(page_urls, message)
            self.assertTrue(all("path=/products" in url and "path=/shop" not in url for url in page_urls))
            handshakes = [event for event in fresh if event["kind"] == "handshake"]
            self.assertEqual(handshakes[0]["detail"]["asked"]["requested_scopes"], ["view"])

    def test_b3_without_a_site_key_shop_still_targets_products(self):
        body = self._chat("open the shop", use_site_key=False)
        self.assertEqual(body["path"], "/products")
        self.assertTrue(body["url"].endswith("/products"))
        self.assertNotIn("/shop", body["url"])


if __name__ == "__main__":
    unittest.main()
