"""Owner dashboard AI endpoints: handshake risk, policy co-pilot, activity summary.

Model calls are mocked. The fallback tests force the Meta client to fail and
expect HTTP 200 with a labelled rules result, not an error.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

SERVER = Path(__file__).resolve().parents[1]
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

import store  # noqa: E402
from app import app  # noqa: E402

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
    "META_TIMEOUT_SECONDS",
    "META_VISION_TIMEOUT_SECONDS",
    "META_MAX_RETRIES",
)


class _Recorder:
    def __init__(self, content: str, error: BaseException | None = None):
        self.content = content
        self.error = error
        self.clients: list[dict] = []
        self.calls: list[dict] = []

    def __enter__(self):
        recorder = self

        class _Completions:
            def create(_self, **kwargs):
                recorder.calls.append(kwargs)
                if recorder.error:
                    raise recorder.error
                msg = MagicMock()
                msg.content = recorder.content
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
            def __init__(_self, **kwargs):
                recorder.clients.append(kwargs)
                _self.chat = _Chat()

        self._patch = patch("muse_client.OpenAI", _Client)
        self._patch.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self._patch.stop()
        return False


GROUNDED_SUMMARY = (
    "2 events from 1 agents show one handshake and one page read by the shop agent today."
)


class OwnerMetaEndpoints(unittest.TestCase):
    def setUp(self):
        self._saved = {key: os.environ.get(key) for key in ENV_KEYS}
        self._dotenv = patch("muse_client.load_dotenv", lambda *args, **kwargs: False)
        self._dotenv.start()
        for key in ENV_KEYS:
            os.environ.pop(key, None)
        os.environ["META_API_KEY"] = "test-meta-key"
        os.environ["META_BASE_URL"] = "https://api.meta.ai/v1"
        os.environ["META_MODEL"] = "muse-spark-1.3"
        os.environ["META_PROVIDER"] = "meta"
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._store = patch.object(store, "STORE_PATH", Path(self._tmp.name) / "store.json")
        self._store.start()
        self.client = app.test_client()
        login = self.client.post(
            "/api/auth/login",
            json={"email": "owner@aurif.dev", "password": "demo1234"},
        )
        self.assertEqual(login.status_code, 200, login.get_data(as_text=True))
        self.headers = {"X-Aurif-Owner": login.get_json()["token"]}
        sites = self.client.get("/api/sites", headers=self.headers).get_json()["sites"]
        self.site = sites[0]
        self.site_id = self.site["id"]

    def tearDown(self):
        self._store.stop()
        self._dotenv.stop()
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def assert_no_secrets(self, payload) -> None:
        blob = json.dumps(payload)
        self.assertNotIn("test-meta-key", blob)
        self.assertNotIn("API_KEY", blob)
        self.assertNotIn(".env", blob)

    def _endpoint(self, site, endpoint_id):
        return next(row for row in site["endpoints"] if row["id"] == endpoint_id)

    def _visible(self, site, endpoint_id, key):
        endpoint = self._endpoint(site, endpoint_id)
        return next(field["agent_visible"] for field in endpoint["response_fields"] if field["key"] == key)

    def test_policy_and_summary_require_login(self):
        anon = app.test_client()
        propose = anon.post(
            f"/api/sites/{self.site_id}/ai/policy-propose",
            json={"instruction": "hide prices"},
        )
        summary = anon.post(f"/api/sites/{self.site_id}/ai/activity-summary", json={})
        self.assertEqual(propose.status_code, 401)
        self.assertEqual(summary.status_code, 401)

    def test_policy_propose_uses_meta_model_and_does_not_apply(self):
        before = self._endpoint(self.site, "page.home")["agent_access"]
        with _Recorder(
            '{"summary":"Close the home page.","patches":[{"endpoint_id":"page.home","agent_access":false}]}'
        ) as rec:
            response = self.client.post(
                f"/api/sites/{self.site_id}/ai/policy-propose",
                headers=self.headers,
                json={"instruction": "turn off the home page"},
            )
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["source"], "model")
        self.assertFalse(body["degraded"])
        self.assertIsNone(body["fallback"])
        self.assertEqual(body["model"], "muse-spark-1.3")
        self.assertEqual(body["model_info"]["label"], "Muse Spark 1.3")
        self.assertEqual(body["model_info"]["provider"], "meta")
        self.assertIsInstance(body["latency_ms"], int)
        self.assertEqual(body["proposal"]["summary"], "Close the home page.")
        self.assertEqual(body["proposal"]["patches"][0]["endpoint_id"], "page.home")
        self.assertEqual(body["proposal"]["source"], "model")
        self.assertEqual(rec.calls[0]["model"], "muse-spark-1.3")
        self.assertEqual(rec.clients[0]["timeout"], 8.0)
        self.assertEqual(rec.clients[0]["api_key"], "test-meta-key")
        self.assert_no_secrets(body)
        after = self.client.get(f"/api/sites/{self.site_id}", headers=self.headers).get_json()["site"]
        self.assertEqual(self._endpoint(after, "page.home")["agent_access"], before)

    def test_policy_propose_falls_back_when_the_model_fails_and_apply_is_separate(self):
        before = self.client.get(f"/api/sites/{self.site_id}", headers=self.headers).get_json()["site"]
        self.assertTrue(self._endpoint(before, "action.cart.checkout")["agent_access"])
        self.assertTrue(self._visible(before, "page.product", "meta.price"))
        with _Recorder("", error=TimeoutError("read timed out")) as rec:
            response = self.client.post(
                f"/api/sites/{self.site_id}/ai/policy-propose",
                headers=self.headers,
                json={"instruction": "Hide prices from agents and disable checkout"},
            )
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["source"], "rules")
        self.assertTrue(body["degraded"])
        self.assertEqual(body["fallback"], "keyword_rules")
        self.assertIn("fallback", body["warning"].lower())
        self.assertIn("not applied", body["warning"].lower())
        self.assertEqual(body["model"], "muse-spark-1.3")
        self.assertEqual(body["proposal"]["model"]["id"], "muse-spark-1.3")
        self.assertEqual(rec.clients[0]["timeout"], 8.0)
        self.assertEqual(len(rec.calls), 1)
        self.assert_no_secrets(body)

        checkout = next(
            patch
            for patch in body["proposal"]["patches"]
            if patch.get("endpoint_id") == "action.cart.checkout"
        )
        self.assertFalse(checkout["agent_access"])
        price_patches = [
            patch for patch in body["proposal"]["patches"] if patch.get("response_fields")
        ]
        self.assertTrue(price_patches)
        hidden = [
            field["key"]
            for patch in price_patches
            for field in patch["response_fields"]
            if field.get("agent_visible") is False and "price" in field["key"]
        ]
        self.assertIn("meta.price", hidden)

        unchanged = self.client.get(f"/api/sites/{self.site_id}", headers=self.headers).get_json()["site"]
        self.assertTrue(self._endpoint(unchanged, "action.cart.checkout")["agent_access"])
        self.assertTrue(self._visible(unchanged, "page.product", "meta.price"))

        applied = self.client.post(
            f"/api/sites/{self.site_id}/ai/policy-apply",
            headers=self.headers,
            json={
                "patches": body["proposal"]["patches"],
                "blocked_agents_add": body["proposal"]["blocked_agents_add"],
            },
        )
        self.assertEqual(applied.status_code, 200)
        site = applied.get_json()["site"]
        self.assertFalse(self._endpoint(site, "action.cart.checkout")["agent_access"])
        self.assertFalse(self._visible(site, "page.product", "meta.price"))
        self.assertTrue(self._endpoint(site, "page.products")["agent_access"])

    def test_empty_policy_instruction_is_rejected(self):
        response = self.client.post(
            f"/api/sites/{self.site_id}/ai/policy-propose",
            headers=self.headers,
            json={"instruction": "  "},
        )
        self.assertEqual(response.status_code, 400)

    def test_activity_summary_uses_meta_model(self):
        store.log_activity(self.site_id, kind="handshake", agent_id="shop-bot", detail={})
        store.log_activity(self.site_id, kind="page", agent_id="shop-bot", detail={})
        payload = json.dumps(
            {
                "summary": GROUNDED_SUMMARY,
                "risks": ["shop-bot stayed inside view"],
                "suggested_blocked_agents": [],
            }
        )
        with _Recorder(payload) as rec:
            response = self.client.post(
                f"/api/sites/{self.site_id}/ai/activity-summary",
                headers=self.headers,
                json={},
            )
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["source"], "model")
        self.assertFalse(body["degraded"])
        self.assertIsNone(body["fallback"])
        self.assertEqual(body["summary"]["summary"], GROUNDED_SUMMARY)
        self.assertEqual(body["model_info"]["label"], "Muse Spark 1.3")
        self.assertIsInstance(body["latency_ms"], int)
        self.assertEqual(rec.calls[0]["model"], "muse-spark-1.3")
        self.assertEqual(rec.clients[0]["timeout"], 8.0)
        self.assert_no_secrets(body)

    def test_activity_summary_falls_back_to_counts_when_the_model_fails(self):
        store.log_activity(self.site_id, kind="handshake", agent_id="shop-bot", detail={})
        store.log_activity(self.site_id, kind="page", agent_id="shop-bot", detail={})
        with _Recorder("", error=TimeoutError("read timed out")) as rec:
            response = self.client.post(
                f"/api/sites/{self.site_id}/ai/activity-summary",
                headers=self.headers,
                json={},
            )
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["source"], "rules")
        self.assertTrue(body["degraded"])
        self.assertEqual(body["fallback"], "activity_counts")
        self.assertIn("fallback", body["warning"].lower())
        self.assertIn("2 events", body["summary"]["summary"])
        self.assertIn("1 handshake", body["summary"]["summary"])
        self.assertEqual(body["model"], "muse-spark-1.3")
        self.assertEqual(body["summary"]["model"]["label"], "Muse Spark 1.3")
        self.assertEqual(len(rec.calls), 1)
        self.assertEqual(rec.clients[0]["timeout"], 8.0)
        self.assert_no_secrets(body)

    def test_handshake_records_model_risk_for_the_dashboard(self):
        with _Recorder(
            '{"risk":"high","reason":"scraping prices for resale","suggested_scopes":["view"],"drop_act":true}'
        ):
            response = self.client.post(
                "/ai/handshake",
                json={
                    "agent_id": "price-bot",
                    "purpose": "help me buy a tote",
                    "requested_scopes": ["view", "act"],
                    "site_key": self.site["site_key"],
                },
            )
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        risk = body["purpose_risk"]
        self.assertEqual(risk["risk"], "high")
        self.assertEqual(risk["reason"], "scraping prices for resale")
        self.assertEqual(risk["source"], "model")
        self.assertFalse(risk["degraded"])
        self.assertEqual(risk["model"]["id"], "muse-spark-1.3")
        self.assertEqual(risk["model"]["label"], "Muse Spark 1.3")
        self.assertIsInstance(risk["latency_ms"], int)
        self.assertNotIn("act", body["granted_scopes"])
        self.assert_no_secrets(body)

        activity = self.client.get(
            f"/api/sites/{self.site_id}/activity",
            headers=self.headers,
        )
        self.assertEqual(activity.status_code, 200)
        event = next(row for row in activity.get_json()["events"] if row["kind"] == "handshake")
        recorded = event["detail"]["purpose_risk"]
        self.assertEqual(recorded["risk"], "high")
        self.assertEqual(recorded["reason"], "scraping prices for resale")
        self.assertEqual(recorded["model"]["id"], "muse-spark-1.3")
        self.assertEqual(event["detail"]["purpose"], "help me buy a tote")

    def test_handshake_fallback_is_labelled_and_keeps_a_shopper_on_act(self):
        with _Recorder("", error=TimeoutError("read timed out")) as rec:
            shop = self.client.post(
                "/ai/handshake",
                json={
                    "agent_id": "shop-bot",
                    "purpose": "help me buy a tote",
                    "requested_scopes": ["view", "act"],
                    "site_key": self.site["site_key"],
                },
            )
            scrape = self.client.post(
                "/ai/handshake",
                json={
                    "agent_id": "scrape-bot",
                    "purpose": "scrape every price for resale",
                    "requested_scopes": ["view", "act"],
                    "site_key": self.site["site_key"],
                },
            )
        self.assertEqual(shop.status_code, 200)
        shop_risk = shop.get_json()["purpose_risk"]
        self.assertEqual(shop_risk["source"], "rules")
        self.assertTrue(shop_risk["degraded"])
        self.assertEqual(shop_risk["fallback"], "keyword_rules")
        self.assertEqual(shop_risk["risk"], "low")
        self.assertIn("act", shop.get_json()["granted_scopes"])
        self.assertEqual(shop_risk["model"]["id"], "muse-spark-1.3")
        self.assertIn("fallback", shop_risk["warning"].lower())
        self.assert_no_secrets(shop.get_json())
        self.assertGreaterEqual(len(rec.calls), 1)
        self.assertEqual(rec.clients[0]["timeout"], 8.0)

        scrape_risk = scrape.get_json()["purpose_risk"]
        self.assertEqual(scrape_risk["risk"], "high")
        self.assertEqual(scrape_risk["fallback"], "keyword_rules")
        self.assertNotIn("act", scrape.get_json()["granted_scopes"])

        activity = self.client.get(
            f"/api/sites/{self.site_id}/activity",
            headers=self.headers,
        ).get_json()["events"]
        shop_event = next(row for row in activity if row["agent_id"] == "shop-bot")
        self.assertEqual(shop_event["detail"]["purpose_risk"]["source"], "rules")
        self.assertTrue(shop_event["detail"]["purpose_risk"]["degraded"])
        self.assertEqual(shop_event["detail"]["purpose_risk"]["model"]["label"], "Muse Spark 1.3")


if __name__ == "__main__":
    unittest.main()
