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

import muse_browse  # noqa: E402
import muse_client  # noqa: E402
import store  # noqa: E402
from app import _muse_report_site_response, app  # noqa: E402

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
    "VISION_MODEL",
    "VISION_BASE_URL",
    "VISION_API_KEY",
    "VISION_PROVIDER",
    "VISION_TIMEOUT_SECONDS",
    "VISION_FALLBACK_MODEL",
    "VISION_FALLBACK_BASE_URL",
    "VISION_FALLBACK_API_KEY",
    "MODAL_VISION_MODEL",
    "MODAL_BASE_URL",
    "MODAL_TOKEN_ID",
    "MODAL_TOKEN_SECRET",
    "BASETEN_API_KEY",
    "BASETEN_MODEL",
    "META_TIMEOUT_SECONDS",
    "META_VISION_TIMEOUT_SECONDS",
    "META_MAX_RETRIES",
)


class _LimitRejected(Exception):
    status_code = 400


class _Recorder:
    def __init__(
        self,
        content: str,
        error: BaseException | None = None,
        *,
        reasoning: str | None = None,
        reject_reasoning_limit: bool = False,
    ):
        self.content = content
        self.error = error
        self.reasoning = reasoning
        self.reject_reasoning_limit = reject_reasoning_limit
        self._rejected_limit = False
        self.clients: list[dict] = []
        self.calls: list[dict] = []

    def __enter__(self):
        recorder = self

        class _Completions:
            def create(_self, **kwargs):
                recorder.calls.append(kwargs)
                extra = kwargs.get("extra_body") or {}
                if (
                    recorder.reject_reasoning_limit
                    and not recorder._rejected_limit
                    and (
                        "chat_template_kwargs" in extra
                        or extra.get("reasoning_effort") == "low"
                    )
                ):
                    recorder._rejected_limit = True
                    raise _LimitRejected("reasoning limit rejected")
                if recorder.error:
                    raise recorder.error
                msg = MagicMock()
                msg.content = recorder.content
                msg.reasoning = None
                msg.reasoning_content = recorder.reasoning
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


# One handshake and one page read by shop-bot. Counts the model must keep.
_SHOP_EVENTS = [
    {"kind": "handshake", "agent_id": "shop-bot", "detail": {}},
    {"kind": "page", "agent_id": "shop-bot", "detail": {}},
]
_SHOP_FACTS = {
    "events": 2,
    "agents": 1,
    "handshakes": 1,
    "page_reads": 1,
    "actions": 0,
    "blocks": 0,
    "field_hides": 0,
    "high_risk_agents": 0,
}


class ActivitySummaryGrounding(unittest.TestCase):
    """Faithful Muse phrasings stay. A changed or invented count does not."""

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

    def tearDown(self):
        self._dotenv.stop()
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _summarize(self, content: str, **recorder_kwargs):
        with _Recorder(content, **recorder_kwargs) as rec:
            result = muse_client.summarize_activity(_SHOP_EVENTS)
        return result, rec

    def test_count_words_reordered_facts_and_extra_prose_pass(self):
        samples = [
            "Two events from one agent included one handshake and one page read.",
            "One page read, then one handshake: two events in all, from a single agent. Nothing else happened.",
            "No actions. One handshake and one page read across two events for one agent, with a little quiet browsing in between.",
        ]
        for text in samples:
            result, rec = self._summarize(
                json.dumps(
                    {
                        "summary": text,
                        "risks": ["The shop agent stayed inside view."],
                        "suggested_blocked_agents": [],
                    }
                )
            )
            self.assertEqual(result["source"], "model", text)
            self.assertFalse(result["degraded"], text)
            self.assertIsNone(result["fallback"], text)
            self.assertEqual(result["summary"], text)
            prompt = rec.calls[0]["messages"][1]["content"]
            self.assertIn('"events": 2', prompt)
            self.assertIn('"handshakes": 1', prompt)
            self.assertIn('"page_reads": 1', prompt)

    def test_plain_prose_with_the_same_counts_passes(self):
        text = (
            "Across this window there were two events from one agent: "
            "one handshake and one page read. No blocks."
        )
        result, _rec = self._summarize(text)
        self.assertEqual(result["source"], "model")
        self.assertEqual(result["summary"], text)
        self.assertIsNone(result["fallback"])

    def test_semantic_checker_accepts_words_and_rejects_a_changed_count(self):
        self.assertTrue(
            muse_client.summary_respects_counts(
                "no actions and one handshake",
                _SHOP_FACTS,
            )
        )
        self.assertTrue(
            muse_client.summary_respects_counts(
                "one page read by the shop agent",
                _SHOP_FACTS,
            )
        )
        self.assertFalse(
            muse_client.summary_respects_counts(
                "no actions",
                {**_SHOP_FACTS, "actions": 2},
            )
        )
        self.assertFalse(muse_client.summary_respects_counts("12 events", _SHOP_FACTS))
        self.assertFalse(
            muse_client.summary_respects_counts(
                "one of the agents did something vague",
                _SHOP_FACTS,
            )
        )

    def test_wrong_count_is_rejected_and_logged_without_secrets(self):
        wrong = [
            "Nine events from one agent, with one handshake and one page read.",
            "2 events from 1 agent: 4 handshakes and 1 page read.",
        ]
        for text in wrong:
            raw = json.dumps(
                {
                    "summary": text + " leak test-meta-key sk-supersecretvalue",
                    "risks": [],
                    "suggested_blocked_agents": [],
                }
            )
            with self.assertLogs("aurif.models", level="DEBUG") as logs:
                result, _rec = self._summarize(raw)
            self.assertEqual(result["source"], "rules", text)
            self.assertFalse(result["degraded"], text)
            self.assertEqual(result["fallback"], "activity_counts", text)
            self.assertIn("counted facts", result["warning"])
            self.assertIn("2 events", result["summary"])
            self.assertIn("1 handshake", result["summary"])
            self.assertNotIn("Nine", result["summary"])
            self.assertNotIn("4 handshake", result["summary"])
            blob = "\n".join(logs.output)
            self.assertIn("activity summary rejected", blob)
            self.assertIn("phrase:", blob)
            self.assertIn(text.split(",")[0][:24], blob)
            self.assertNotIn("test-meta-key", blob)
            self.assertNotIn("sk-supersecretvalue", blob)
            self.assertIn("[redacted]", blob)

    def test_a_wrong_count_inside_a_risk_bullet_rejects_the_reply(self):
        raw = json.dumps(
            {
                "summary": "Two events from one agent included one handshake and one page read.",
                "risks": ["Twelve events look like scraping."],
                "suggested_blocked_agents": [],
            }
        )
        result, _rec = self._summarize(raw)
        self.assertEqual(result["source"], "rules")
        self.assertEqual(result["fallback"], "activity_counts")
        self.assertIn("2 events", result["summary"])
        self.assertNotIn("Twelve", result["summary"])

    def test_reasoning_without_content_falls_back(self):
        reasoning = "Restating the prompt: use only the counted facts and return JSON."
        with self.assertLogs("aurif.models", level="WARNING") as logs:
            result, rec = self._summarize("", reasoning=reasoning)
        self.assertEqual(result["source"], "rules")
        self.assertTrue(result["degraded"])
        self.assertEqual(result["fallback"], "activity_counts")
        self.assertIn("2 events", result["summary"])
        self.assertNotIn("Restating the prompt", result["summary"])
        blob = "\n".join(logs.output)
        self.assertIn("model returned only reasoning", blob)
        self.assertNotIn("model request failed", blob)
        self.assertNotIn("model unavailable", blob.lower())
        self.assertEqual(rec.calls[0]["max_tokens"], 2048)
        self.assertEqual(rec.clients[0]["timeout"], 8.0)
        self.assertNotIn("chat_template_kwargs", rec.calls[0].get("extra_body") or {})

    def test_content_summary_is_kept_when_reasoning_is_also_present(self):
        text = "Two events from one agent included one handshake and one page read."
        payload = json.dumps(
            {"summary": text, "risks": [], "suggested_blocked_agents": []}
        )
        result, rec = self._summarize(
            payload,
            reasoning="I will spend the whole budget restating the prompt before I answer.",
        )
        self.assertEqual(result["source"], "model")
        self.assertFalse(result["degraded"])
        self.assertIsNone(result["fallback"])
        self.assertEqual(result["summary"], text)
        self.assertNotIn("restating the prompt", result["summary"].lower())
        self.assertEqual(rec.calls[0]["max_tokens"], 2048)
        self.assertEqual(rec.clients[0]["timeout"], 8.0)
        self.assertEqual(len(rec.calls), 1)

    def test_baseten_retries_summary_without_a_rejected_reasoning_limit(self):
        os.environ.pop("META_API_KEY", None)
        os.environ.pop("META_BASE_URL", None)
        os.environ.pop("META_MODEL", None)
        os.environ.pop("META_PROVIDER", None)
        os.environ["BASETEN_API_KEY"] = "test-baseten-key"
        text = "Two events from one agent included one handshake and one page read."
        payload = json.dumps(
            {"summary": text, "risks": [], "suggested_blocked_agents": []}
        )
        result, rec = self._summarize(payload, reject_reasoning_limit=True)
        self.assertEqual(result["source"], "model")
        self.assertEqual(result["summary"], text)
        self.assertEqual(len(rec.calls), 2)
        self.assertEqual(rec.calls[0]["max_tokens"], 2048)
        self.assertEqual(rec.calls[0]["extra_body"]["reasoning_effort"], "low")
        self.assertEqual(
            rec.calls[0]["extra_body"]["chat_template_kwargs"],
            {"reasoning_effort": "low"},
        )
        self.assertNotIn("extra_body", rec.calls[1])
        self.assertEqual(rec.calls[1]["max_tokens"], 2048)
        self.assertEqual(rec.clients[0]["timeout"], 8.0)
        self.assertEqual(rec.clients[0]["base_url"], "https://inference.baseten.co/v1")

    def test_version_digits_and_sentence_breaks_are_not_counts(self):
        facts = {**_SHOP_FACTS, "high_risk_agents": 1}
        versioned = (
            "Two events from one agent included one handshake and one page read. "
            "price-harvester/0.9 High-risk agent detected."
        )
        hidden = (
            "Two events from one agent included one handshake and one page read. "
            "No fields hidden. High-risk agent detected."
        )
        self.assertTrue(muse_client.summary_respects_counts(versioned, facts))
        self.assertTrue(muse_client.summary_respects_counts(hidden, facts))
        self.assertFalse(
            muse_client.summary_respects_counts("No high-risk agents.", facts)
        )
        events = [
            {
                "kind": "handshake",
                "agent_id": "price-harvester/0.9",
                "detail": {"purpose_risk": {"risk": "high", "reason": "scraping"}},
            },
            {"kind": "page", "agent_id": "price-harvester/0.9", "detail": {}},
        ]
        for text in (versioned, hidden):
            payload = json.dumps(
                {"summary": text, "risks": [], "suggested_blocked_agents": []}
            )
            with _Recorder(payload):
                result = muse_client.summarize_activity(events)
            self.assertEqual(result["source"], "model", text)
            self.assertEqual(result["summary"], text)

    def test_handshake_reasoning_only_is_logged_without_a_request_failure(self):
        reasoning = "Only reasoning, about 255 characters, no final answer."
        with self.assertLogs("aurif.models", level="WARNING") as logs:
            with _Recorder("", reasoning=reasoning) as rec:
                result = muse_client.score_purpose("compare tote prices")
        blob = "\n".join(logs.output)
        self.assertEqual(result["source"], "rules")
        self.assertTrue(result["degraded"])
        self.assertEqual(result["fallback"], "keyword_rules")
        self.assertIn("model returned only reasoning", blob)
        self.assertNotIn("model request failed", blob)
        self.assertNotIn("model unavailable", blob.lower())
        self.assertEqual(rec.calls[0]["max_tokens"], 2048)
        self.assertEqual(rec.clients[0]["timeout"], 8.0)
        self.assertNotIn(reasoning, result["reason"])

    def test_handshake_keeps_model_content_for_a_shopper_question(self):
        payload = (
            '{"risk":"low","reason":"comparing tote prices for a shopper",'
            '"suggested_scopes":["view","act"],"drop_act":false}'
        )
        with _Recorder(payload, reasoning="thinking about stock and prices") as rec:
            result = muse_client.score_purpose("check if the field tote is in stock")
        self.assertEqual(result["source"], "model")
        self.assertEqual(result["risk"], "low")
        self.assertFalse(result["drop_act"])
        self.assertIn("act", result["suggested_scopes"])
        self.assertEqual(rec.calls[0]["max_tokens"], 2048)
        self.assertEqual(rec.clients[0]["timeout"], 8.0)

    def test_browse_polish_reasoning_only_uses_the_field_answer(self):
        fields = [
            {"label": "name", "value": "Field Tote"},
            {"label": "price", "value": "$68"},
        ]
        reasoning = "Products: Field Tote (68). Name: Field Tote; Title: Tote; Sku: FT."
        with self.assertLogs("aurif.models", level="WARNING") as logs:
            with _Recorder("", reasoning=reasoning) as rec:
                reply = muse_browse._compose_reply(
                    message="how much is the field tote",
                    steps=[],
                    fields=fields,
                    denied=False,
                )
        blob = "\n".join(logs.output)
        self.assertIn("68", reply)
        self.assertNotIn("Sku", reply)
        self.assertNotIn("Products:", reply)
        self.assertIn("model returned only reasoning", blob)
        self.assertNotIn("model request failed", blob)
        self.assertNotIn("model unavailable", blob.lower())
        self.assertEqual(rec.calls[0]["max_tokens"], 1024)

    def test_baseten_budgets_and_reasoning_control_on_every_muse_call(self):
        os.environ.pop("META_API_KEY", None)
        os.environ.pop("META_BASE_URL", None)
        os.environ.pop("META_MODEL", None)
        os.environ.pop("META_PROVIDER", None)
        os.environ["BASETEN_API_KEY"] = "test-baseten-key"

        def extra_ok(call: dict) -> None:
            extra = call["extra_body"]
            self.assertEqual(extra["reasoning_effort"], "low")
            self.assertEqual(extra["chat_template_kwargs"], {"reasoning_effort": "low"})

        with _Recorder(
            '{"risk":"low","reason":"shopper","suggested_scopes":["view","act"],"drop_act":false}'
        ) as rec:
            muse_client.score_purpose("compare tote prices")
        self.assertEqual(rec.calls[0]["max_tokens"], 2048)
        self.assertEqual(rec.clients[0]["timeout"], 8.0)
        extra_ok(rec.calls[0])

        with _Recorder('{"summary":"Hide prices.","patches":[],"blocked_agents_add":[]}') as rec:
            muse_client.propose_policy("hide prices", [])
        self.assertEqual(rec.calls[0]["max_tokens"], 2500)
        extra_ok(rec.calls[0])

        with _Recorder(
            json.dumps(
                {
                    "summary": "Two events from one agent included one handshake and one page read.",
                    "risks": [],
                    "suggested_blocked_agents": [],
                }
            )
        ) as rec:
            muse_client.summarize_activity(_SHOP_EVENTS)
        self.assertEqual(rec.calls[0]["max_tokens"], 2048)
        extra_ok(rec.calls[0])

        fields = [
            {"label": "name", "value": "Field Tote"},
            {"label": "price", "value": "$68"},
        ]
        with _Recorder("The price of Field Tote is $68.") as rec:
            muse_browse._compose_reply(
                message="how much is the field tote",
                steps=[],
                fields=fields,
                denied=False,
            )
        self.assertEqual(rec.calls[0]["max_tokens"], 1024)
        extra_ok(rec.calls[0])

        with _Recorder(
            "I can see the product name and the listed price on this page for the owner."
        ) as rec:
            _muse_report_site_response(
                "Name: Field Tote; Title: Tote; Sku: FT-1.",
                seen_fields=[("Name", "Field Tote")],
            )
        self.assertEqual(rec.calls[0]["max_tokens"], 1024)
        extra_ok(rec.calls[0])


if __name__ == "__main__":
    unittest.main()
