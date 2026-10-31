"""Mocked checks that every LLM call site targets the configured Meta model."""

from __future__ import annotations

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
from app import _muse_report_site_response  # noqa: E402

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
    "MODAL_VISION_MODEL",
    "MODAL_BASE_URL",
    "MODAL_TOKEN_ID",
    "MODAL_TOKEN_SECRET",
    "BASETEN_API_KEY",
    "BASETEN_MODEL",
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


class MetaModelCallSites(unittest.TestCase):
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

    def assert_meta_request(self, recorder: _Recorder, *, model: str, base_url: str, api_key: str):
        self.assertTrue(recorder.clients, "OpenAI client was not constructed")
        self.assertEqual(recorder.clients[0]["base_url"], base_url)
        self.assertEqual(recorder.clients[0]["api_key"], api_key)
        self.assertTrue(recorder.calls, "chat.completions.create was not called")
        self.assertEqual(recorder.calls[0]["model"], model)
        self.assertNotIn("deepseek", recorder.calls[0]["model"].lower())
        self.assertNotIn("top_p", recorder.calls[0])
        joined = str(recorder.calls[0])
        self.assertNotIn("deepseek", joined.lower())

    def test_score_purpose_posts_to_configured_meta_model(self):
        with _Recorder(
            '{"risk":"low","reason":"shopper help","suggested_scopes":["view"],"drop_act":false}'
        ) as rec:
            result = muse_client.score_purpose("help a user buy a tote")
        self.assertEqual(result["risk"], "low")
        self.assert_meta_request(
            rec,
            model="muse-spark-1.3",
            base_url="https://api.meta.ai/v1",
            api_key="test-meta-key",
        )
        self.assertEqual(rec.calls[0]["extra_body"], {"reasoning_effort": "low"})

    def test_propose_policy_posts_to_configured_meta_model(self):
        endpoints = [
            {
                "id": "page.home",
                "label": "Home",
                "kind": "page",
                "agent_access": True,
                "response_fields": [],
                "request_fields": [],
            }
        ]
        with _Recorder(
            '{"summary":"Close home","patches":[{"endpoint_id":"page.home","agent_access":false}]}'
        ) as rec:
            result = muse_client.propose_policy("turn off the home page", endpoints)
        self.assertEqual(result["summary"], "Close home")
        self.assertEqual(result["patches"][0]["endpoint_id"], "page.home")
        self.assert_meta_request(
            rec,
            model="muse-spark-1.3",
            base_url="https://api.meta.ai/v1",
            api_key="test-meta-key",
        )

    def test_summarize_activity_posts_to_configured_meta_model(self):
        events = [{"kind": "handshake", "agent_id": "shop-bot", "detail": {}}]
        with _Recorder('{"summary":"ignored","risks":[],"suggested_blocked_agents":[]}') as rec:
            muse_client.summarize_activity(events)
        self.assert_meta_request(
            rec,
            model="muse-spark-1.3",
            base_url="https://api.meta.ai/v1",
            api_key="test-meta-key",
        )

    def test_compose_reply_posts_to_configured_meta_model(self):
        with _Recorder("The price is $10.") as rec:
            reply = muse_browse._compose_reply(
                message="what is the price",
                steps=[],
                fields=[{"label": "Price", "value": "$10"}],
                denied=False,
            )
        self.assertIn("10", reply)
        self.assert_meta_request(
            rec,
            model="muse-spark-1.3",
            base_url="https://api.meta.ai/v1",
            api_key="test-meta-key",
        )

    def test_page_report_posts_to_configured_meta_model(self):
        with _Recorder(
            "I can see the product name and the listed price on this page for the owner."
        ) as rec:
            text = _muse_report_site_response(
                "Here's what the site showed me:\n- Name: Field Tote",
                seen_fields=[("Name", "Field Tote")],
            )
        self.assertIn("product", text.lower())
        self.assert_meta_request(
            rec,
            model="muse-spark-1.3",
            base_url="https://api.meta.ai/v1",
            api_key="test-meta-key",
        )

    def test_verify_drawing_posts_image_to_configured_meta_model(self):
        image = "data:image/png;base64,iVBORw0KGgo="
        with _Recorder(
            '{"match":true,"human_like":true,"read_as":"A","reason":"ok"}'
        ) as rec:
            verdict = muse_client.verify_drawing(image, "A")
        self.assertTrue(verdict["ok"])
        self.assertEqual(verdict["model"], "muse-spark-1.3")
        self.assertEqual(verdict["provider"], "meta")
        self.assert_meta_request(
            rec,
            model="muse-spark-1.3",
            base_url="https://api.meta.ai/v1",
            api_key="test-meta-key",
        )
        content = rec.calls[0]["messages"][1]["content"]
        self.assertEqual(content[1]["type"], "image_url")
        self.assertEqual(content[1]["image_url"]["url"], image)

    def test_vision_override_is_independent_of_text_model(self):
        os.environ["META_VISION_API_KEY"] = "vision-key"
        os.environ["META_VISION_BASE_URL"] = "https://vision.example.test/v1"
        os.environ["META_VISION_MODEL"] = "meta-llama/Llama-4-Scout"
        os.environ["META_VISION_PROVIDER"] = "llama"
        image = "data:image/png;base64,iVBORw0KGgo="
        with _Recorder('{"match":false,"human_like":true,"read_as":"B","reason":"wrong"}') as rec:
            muse_client.verify_drawing(image, "A")
        self.assert_meta_request(
            rec,
            model="meta-llama/Llama-4-Scout",
            base_url="https://vision.example.test/v1",
            api_key="vision-key",
        )
        with _Recorder(
            '{"risk":"high","reason":"scrape","suggested_scopes":["view"],"drop_act":true}'
        ) as text_rec:
            muse_client.score_purpose("scrape every price")
        self.assert_meta_request(
            text_rec,
            model="muse-spark-1.3",
            base_url="https://api.meta.ai/v1",
            api_key="test-meta-key",
        )

    def test_model_api_key_alias_is_accepted(self):
        os.environ.pop("META_API_KEY", None)
        os.environ["MODEL_API_KEY"] = "official-meta-key"
        with _Recorder(
            '{"risk":"low","reason":"ok","suggested_scopes":["view"],"drop_act":false}'
        ) as rec:
            muse_client.score_purpose("browse")
        self.assertEqual(rec.clients[0]["api_key"], "official-meta-key")
        self.assertEqual(rec.calls[0]["model"], "muse-spark-1.3")

    def test_legacy_deepseek_env_is_ignored(self):
        os.environ["MODAL_VISION_MODEL"] = "deepseek-ai/DeepSeek-V4.1-Flash"
        os.environ["MODAL_BASE_URL"] = (
            "https://anubhavvashishtha-iitd--ep-deepseek-v4-1-flash-server.us-west.modal.direct/v1"
        )
        os.environ["MODAL_TOKEN_ID"] = "tid"
        os.environ["MODAL_TOKEN_SECRET"] = "secret"
        os.environ["BASETEN_API_KEY"] = "baseten-should-not-be-used"
        os.environ["BASETEN_MODEL"] = "deepseek-ai/DeepSeek-V4.1-Flash"
        image = "data:image/png;base64,iVBORw0KGgo="
        with _Recorder('{"match":true,"human_like":true,"read_as":"K","reason":"ok"}') as rec:
            verdict = muse_client.verify_drawing(image, "K")
        self.assertTrue(verdict["ok"])
        self.assertEqual(verdict["model"], "muse-spark-1.3")
        self.assert_meta_request(
            rec,
            model="muse-spark-1.3",
            base_url="https://api.meta.ai/v1",
            api_key="test-meta-key",
        )
        self.assertEqual(len(rec.clients), 1)

    def test_vision_misconfigured_does_not_call_or_fall_back(self):
        os.environ.pop("META_API_KEY", None)
        os.environ.pop("MODEL_API_KEY", None)
        os.environ.pop("META_VISION_API_KEY", None)
        image = "data:image/png;base64,iVBORw0KGgo="
        with _Recorder('{"match":true}') as rec:
            verdict = muse_client.verify_drawing(image, "A")
        self.assertFalse(verdict["ok"])
        self.assertIn("vision provider misconfigured", verdict["reason"])
        self.assertEqual(rec.clients, [])
        self.assertEqual(rec.calls, [])

    def test_deepseek_vision_model_is_rejected_without_a_request(self):
        os.environ["META_VISION_MODEL"] = "deepseek-ai/DeepSeek-V4.1-Flash"
        image = "data:image/png;base64,iVBORw0KGgo="
        with _Recorder('{"match":true}') as rec:
            verdict = muse_client.verify_drawing(image, "A")
        self.assertFalse(verdict["ok"])
        self.assertIn("DeepSeek", verdict["reason"])
        self.assertEqual(rec.calls, [])

    def test_vision_upstream_error_does_not_fall_back(self):
        image = "data:image/png;base64,iVBORw0KGgo="
        with _Recorder("", error=RuntimeError("upstream down")) as rec:
            verdict = muse_client.verify_drawing(image, "A")
        self.assertFalse(verdict["ok"])
        self.assertIn("upstream down", verdict["reason"])
        self.assertIn("vision provider error", verdict["reason"])
        self.assertNotIn("fallback", verdict["reason"].lower())
        self.assertEqual(len(rec.clients), 1)
        self.assertEqual(len(rec.calls), 1)
        self.assertEqual(rec.calls[0]["model"], "muse-spark-1.3")

    def test_human_verify_returns_502_when_vision_is_misconfigured(self):
        import store
        from app import app
        from human_gate import issue_challenge

        os.environ.pop("META_API_KEY", None)
        os.environ.pop("MODEL_API_KEY", None)
        os.environ.pop("META_VISION_API_KEY", None)
        challenge = issue_challenge()
        with tempfile.TemporaryDirectory() as tmp:
            store_path = Path(tmp) / "store.json"
            with patch.object(store, "STORE_PATH", store_path):
                response = app.test_client().post(
                    "/api/public/human-verify",
                    json={
                        "challenge_id": challenge["challenge_id"],
                        "image": "data:image/png;base64,iVBORw0KGgo=",
                    },
                )
        self.assertEqual(response.status_code, 502)
        body = response.get_json()
        self.assertIn("vision provider misconfigured", body["error"])
        self.assertNotIn("agent_access", body)

    def test_non_meta_chat_model_is_rejected(self):
        with _Recorder("nope") as rec:
            with self.assertRaises(RuntimeError) as raised:
                muse_client.resolve_model("deepseek-ai/DeepSeek-V4.1-Flash")
        self.assertIn("DeepSeek", str(raised.exception))
        self.assertEqual(rec.calls, [])


if __name__ == "__main__":
    unittest.main()
