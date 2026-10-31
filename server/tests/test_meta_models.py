"""Mocked checks that every LLM call site targets the configured Meta model."""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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
    "VISION_MODEL",
    "VISION_BASE_URL",
    "VISION_API_KEY",
    "VISION_PROVIDER",
    "VISION_TIMEOUT_SECONDS",
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
        os.environ["BASETEN_API_KEY"] = "test-baseten-key"
        muse_client.reset_model_status()

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
        self.assertEqual(result["source"], "model")
        self.assertFalse(result["degraded"])
        self.assertEqual(rec.clients[0]["timeout"], 8.0)
        self.assertEqual(rec.clients[0]["max_retries"], 0)
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

    def test_verify_drawing_posts_image_to_configured_vision_model(self):
        image = "data:image/png;base64,iVBORw0KGgo="
        with _Recorder(
            '{"match":true,"human_like":true,"read_as":"A","reason":"ok"}'
        ) as rec:
            verdict = muse_client.verify_drawing(image, "A")
        self.assertTrue(verdict["ok"])
        self.assertEqual(verdict["model"], "deepseek-ai/DeepSeek-V4.1-Flash-1017")
        self.assertEqual(verdict["provider"], "baseten")
        self.assertEqual(verdict["family"], "deepseek")
        self.assertEqual(verdict["powered_by"], "DeepSeek V4.1 Flash")
        self.assertNotIn("Meta", verdict["powered_by"])
        self.assertEqual(rec.clients[0]["timeout"], 15.0)
        self.assertEqual(rec.clients[0]["max_retries"], 0)
        self.assertEqual(rec.clients[0]["base_url"], "https://inference.baseten.co/v1")
        self.assertEqual(rec.clients[0]["api_key"], "test-baseten-key")
        self.assertEqual(rec.calls[0]["model"], "deepseek-ai/DeepSeek-V4.1-Flash-1017")
        self.assertNotIn("extra_body", rec.calls[0])
        self.assertNotIn("top_p", rec.calls[0])
        content = rec.calls[0]["messages"][1]["content"]
        self.assertEqual(content[1]["type"], "image_url")
        self.assertEqual(content[1]["image_url"]["url"], image)
        self.assertIn("strict", content[0]["text"].lower())

    def test_non_matching_drawing_is_rejected_and_matching_one_passes(self):
        image = "data:image/png;base64,iVBORw0KGgo="
        with _Recorder(
            '{"match":true,"human_like":true,"read_as":"house","reason":"ok"}'
        ) as rec:
            missed = muse_client.verify_drawing(image, "A")
        self.assertFalse(missed["ok"])
        self.assertFalse(missed["unavailable"])
        self.assertEqual(rec.calls[0]["model"], "deepseek-ai/DeepSeek-V4.1-Flash-1017")
        self.assertEqual(rec.clients[0]["base_url"], "https://inference.baseten.co/v1")

        with _Recorder(
            '{"match":false,"human_like":true,"read_as":"A","reason":"wrong object"}'
        ):
            denied = muse_client.verify_drawing(image, "A")
        self.assertFalse(denied["ok"])
        self.assertFalse(denied["match"])

        with _Recorder(
            '{"match":true,"human_like":true,"read_as":"","reason":"scribble"}'
        ):
            scribbled = muse_client.verify_drawing(image, "A")
        self.assertFalse(scribbled["ok"])

        with _Recorder(
            '{"match":"false","human_like":"true","read_as":"A","reason":"blank"}'
        ):
            blank = muse_client.verify_drawing(image, "A")
        self.assertFalse(blank["ok"])

        with _Recorder(
            '{"match":true,"human_like":true,"read_as":"A","confidence":0.4,"reason":"ok"}'
        ):
            unsure = muse_client.verify_drawing(image, "A")
        self.assertFalse(unsure["ok"])

        with _Recorder(
            '{"match":true,"human_like":true,"read_as":"A","reason":"ok"}'
        ) as rec:
            passed = muse_client.verify_drawing(image, "A")
        self.assertTrue(passed["ok"])
        self.assertEqual(passed["read_as"], "A")
        self.assertEqual(rec.calls[0]["model"], "deepseek-ai/DeepSeek-V4.1-Flash-1017")

    def test_vision_env_is_independent_of_the_text_model(self):
        os.environ["VISION_MODEL"] = "example/sam-3.1"
        os.environ["VISION_BASE_URL"] = "https://vision.example.test/v1"
        os.environ["VISION_API_KEY"] = "vision-key"
        os.environ["VISION_PROVIDER"] = "sam"
        image = "data:image/png;base64,iVBORw0KGgo="
        with _Recorder(
            '{"match":true,"human_like":true,"read_as":"K","reason":"ok"}'
        ) as rec:
            verdict = muse_client.verify_drawing(image, "K")
        self.assertTrue(verdict["ok"])
        self.assertEqual(verdict["model"], "example/sam-3.1")
        self.assertEqual(verdict["provider"], "sam")
        self.assertEqual(verdict["family"], "other")
        self.assertNotIn("Meta", verdict["powered_by"])
        self.assertEqual(rec.clients[0]["base_url"], "https://vision.example.test/v1")
        self.assertEqual(rec.clients[0]["api_key"], "vision-key")
        self.assertEqual(rec.calls[0]["model"], "example/sam-3.1")
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

    def _use_baseten_only(self, model: str | None = None) -> None:
        for key in (
            "META_API_KEY",
            "MODEL_API_KEY",
            "META_BASE_URL",
            "META_MODEL",
            "META_PROVIDER",
            "META_VISION_API_KEY",
            "META_VISION_BASE_URL",
            "META_VISION_MODEL",
            "META_VISION_PROVIDER",
        ):
            os.environ.pop(key, None)
        os.environ["BASETEN_API_KEY"] = "baseten-key"
        if model is None:
            os.environ.pop("BASETEN_MODEL", None)
        else:
            os.environ["BASETEN_MODEL"] = model

    def test_baseten_key_serves_text_on_muse_and_vision_on_deepseek(self):
        self._use_baseten_only()
        os.environ["MODAL_VISION_MODEL"] = "deepseek-ai/DeepSeek-V4.1-Flash"
        os.environ["MODAL_BASE_URL"] = (
            "https://anubhavvashishtha-iitd--ep-deepseek-v4-1-flash-server.us-west.modal.direct/v1"
        )
        image = "data:image/png;base64,iVBORw0KGgo="
        with _Recorder(
            '{"match":true,"human_like":true,"read_as":"A","reason":"ok"}'
        ) as rec:
            verdict = muse_client.verify_drawing(image, "A")
        self.assertTrue(verdict["ok"])
        self.assertEqual(verdict["provider"], "baseten")
        self.assertEqual(verdict["family"], "deepseek")
        self.assertEqual(verdict["model"], "deepseek-ai/DeepSeek-V4.1-Flash-1017")
        self.assertNotIn("modal", rec.clients[0]["base_url"])
        self.assertEqual(rec.clients[0]["base_url"], "https://inference.baseten.co/v1")
        self.assertEqual(rec.clients[0]["api_key"], "baseten-key")
        self.assertEqual(rec.calls[0]["model"], "deepseek-ai/DeepSeek-V4.1-Flash-1017")
        self.assertNotIn("extra_body", rec.calls[0])
        with _Recorder(
            '{"risk":"low","reason":"ok","suggested_scopes":["view"],"drop_act":false}'
        ) as text_rec:
            muse_client.score_purpose("help a shopper")
        self.assert_meta_request(
            text_rec,
            model="meta-models/muse-spark-open-1026",
            base_url="https://inference.baseten.co/v1",
            api_key="baseten-key",
        )
        catalog = muse_client.list_agent_models()
        self.assertEqual(catalog[0]["label"], "Muse Spark Open")
        self.assertEqual(catalog[0]["provider"], "baseten")
        self.assertNotIn("deepseek", catalog[0]["id"].lower())

    def test_baseten_model_env_overrides_the_dated_default(self):
        self._use_baseten_only("meta-models/muse-spark-open")
        with _Recorder(
            '{"risk":"low","reason":"ok","suggested_scopes":["view"],"drop_act":false}'
        ) as rec:
            muse_client.score_purpose("browse")
        self.assertEqual(rec.calls[0]["model"], "meta-models/muse-spark-open")
        self.assertEqual(rec.clients[0]["base_url"], "https://inference.baseten.co/v1")

    def test_baseten_deepseek_model_is_refused_for_text_only(self):
        self._use_baseten_only("deepseek-ai/DeepSeek-V4.1-Flash")
        image = "data:image/png;base64,iVBORw0KGgo="
        with _Recorder(
            '{"match":true,"human_like":true,"read_as":"A","reason":"ok"}'
        ) as rec:
            verdict = muse_client.verify_drawing(image, "A")
            scored = muse_client.score_purpose("browse")
        self.assertTrue(verdict["ok"])
        self.assertEqual(verdict["model"], "deepseek-ai/DeepSeek-V4.1-Flash-1017")
        self.assertEqual(rec.calls[0]["model"], "deepseek-ai/DeepSeek-V4.1-Flash-1017")
        self.assertEqual(scored["source"], "rules")
        self.assertNotIn("DeepSeek", scored["reason"])
        self.assertEqual(len(rec.calls), 1)

    def test_meta_key_wins_over_baseten_key(self):
        os.environ.pop("META_BASE_URL", None)
        os.environ.pop("META_MODEL", None)
        os.environ.pop("META_PROVIDER", None)
        os.environ["META_API_KEY"] = "meta-key"
        os.environ["BASETEN_API_KEY"] = "baseten-key"
        os.environ["BASETEN_MODEL"] = "meta-models/muse-spark-open-1026"
        with _Recorder(
            '{"risk":"low","reason":"ok","suggested_scopes":["view"],"drop_act":false}'
        ) as rec:
            muse_client.score_purpose("browse")
        self.assert_meta_request(
            rec,
            model="muse-spark-1.3",
            base_url="https://api.meta.ai/v1",
            api_key="meta-key",
        )

    def test_startup_log_and_providers_keep_baseten_field(self):
        self._use_baseten_only()
        with self.assertLogs("aurif.models", level="INFO") as logs:
            muse_client.log_active_models()
        text = "\n".join(logs.output)
        self.assertIn("Aurif text model: provider=baseten", text)
        self.assertIn("Aurif vision model: provider=baseten", text)
        self.assertIn("model=meta-models/muse-spark-open-1026", text)
        self.assertIn("model=deepseek-ai/DeepSeek-V4.1-Flash-1017", text)
        self.assertIn("family=deepseek", text)
        self.assertIn("label=DeepSeek V4.1 Flash", text)
        self.assertIn("base_url=https://inference.baseten.co/v1", text)
        self.assertIn("key=set", text)
        self.assertNotIn("baseten-key", text)
        vision_line = next(line for line in logs.output if "Aurif vision model:" in line)
        self.assertNotIn("family=meta", vision_line)
        self.assertNotIn("Powered by Meta", vision_line)
        providers = muse_client.api_providers()
        self.assertEqual(providers["text"]["model"], "meta-models/muse-spark-open-1026")
        self.assertEqual(providers["text"]["family"], "meta")
        self.assertTrue(providers["text"]["powered_by"].startswith("Meta "))
        self.assertEqual(providers["vision"]["provider"], "baseten")
        self.assertEqual(providers["vision"]["model"], "deepseek-ai/DeepSeek-V4.1-Flash-1017")
        self.assertEqual(providers["vision"]["family"], "deepseek")
        self.assertEqual(providers["vision"]["powered_by"], "DeepSeek V4.1 Flash")
        self.assertNotIn("Meta", providers["vision"]["powered_by"])
        self.assertEqual(
            providers["baseten"]["base_url"], "https://inference.baseten.co/v1"
        )
        self.assertNotIn("modal", providers)
        health = muse_client.health_snapshot()
        self.assertEqual(health["text"]["model"], "meta-models/muse-spark-open-1026")
        self.assertEqual(health["text"]["family"], "meta")
        self.assertTrue(health["text"]["powered_by"].startswith("Meta "))
        self.assertEqual(health["vision"]["model"], "deepseek-ai/DeepSeek-V4.1-Flash-1017")
        self.assertEqual(health["vision"]["family"], "deepseek")
        self.assertEqual(health["vision"]["powered_by"], "DeepSeek V4.1 Flash")
        self.assertNotIn("Meta", health["vision"]["powered_by"])
        self.assertNotIn("baseten-key", str(health))

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
        self.assertEqual(verdict["model"], "deepseek-ai/DeepSeek-V4.1-Flash-1017")
        self.assertNotEqual(verdict["model"], os.environ["MODAL_VISION_MODEL"])
        self.assertEqual(rec.clients[0]["base_url"], "https://inference.baseten.co/v1")
        self.assertNotIn("modal", rec.clients[0]["base_url"])
        self.assertEqual(rec.clients[0]["api_key"], "baseten-should-not-be-used")
        self.assertEqual(rec.calls[0]["model"], "deepseek-ai/DeepSeek-V4.1-Flash-1017")
        self.assertEqual(len(rec.clients), 1)
        with _Recorder(
            '{"risk":"low","reason":"ok","suggested_scopes":["view"],"drop_act":false}'
        ) as text_rec:
            muse_client.score_purpose("browse the catalog")
        self.assert_meta_request(
            text_rec,
            model="muse-spark-1.3",
            base_url="https://api.meta.ai/v1",
            api_key="test-meta-key",
        )

    def test_vision_misconfigured_does_not_call_or_fall_back(self):
        os.environ.pop("META_API_KEY", None)
        os.environ.pop("MODEL_API_KEY", None)
        os.environ.pop("META_VISION_API_KEY", None)
        os.environ.pop("VISION_API_KEY", None)
        os.environ.pop("BASETEN_API_KEY", None)
        image = "data:image/png;base64,iVBORw0KGgo="
        with _Recorder('{"match":true}') as rec:
            verdict = muse_client.verify_drawing(image, "A")
        self.assertFalse(verdict["ok"])
        self.assertIn("vision provider misconfigured", verdict["reason"])
        self.assertEqual(rec.clients, [])
        self.assertEqual(rec.calls, [])

    def test_meta_vision_override_still_accepts_a_deepseek_id(self):
        os.environ["META_VISION_MODEL"] = "deepseek-ai/DeepSeek-V4.1-Flash"
        os.environ["META_VISION_BASE_URL"] = "https://inference.baseten.co/v1"
        os.environ["META_VISION_API_KEY"] = "legacy-vision-key"
        image = "data:image/png;base64,iVBORw0KGgo="
        with _Recorder(
            '{"match":true,"human_like":true,"read_as":"A","reason":"ok"}'
        ) as rec:
            verdict = muse_client.verify_drawing(image, "A")
        self.assertTrue(verdict["ok"])
        self.assertEqual(verdict["model"], "deepseek-ai/DeepSeek-V4.1-Flash")
        self.assertEqual(verdict["family"], "deepseek")
        self.assertNotIn("Meta", verdict["powered_by"])
        self.assertEqual(rec.calls[0]["model"], "deepseek-ai/DeepSeek-V4.1-Flash")
        self.assertEqual(rec.clients[0]["api_key"], "legacy-vision-key")
        self.assertEqual(rec.clients[0]["base_url"], "https://inference.baseten.co/v1")

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
        self.assertEqual(rec.calls[0]["model"], "deepseek-ai/DeepSeek-V4.1-Flash-1017")
        self.assertEqual(rec.clients[0]["base_url"], "https://inference.baseten.co/v1")

    def _clear_model_keys(self) -> None:
        for key in (
            "META_API_KEY",
            "MODEL_API_KEY",
            "META_VISION_API_KEY",
            "VISION_API_KEY",
            "BASETEN_API_KEY",
        ):
            os.environ.pop(key, None)

    def _ink_png(self) -> str:
        import base64
        from io import BytesIO

        from PIL import Image

        image = Image.new("L", (48, 48), 255)
        for x in range(6, 36):
            image.putpixel((x, 24), 0)
        buf = BytesIO()
        image.save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

    def test_blank_drawing_explains_fallback_when_vision_is_down(self):
        import store
        from app import app
        from human_gate import issue_challenge, peek_challenge

        self._clear_model_keys()
        challenge = issue_challenge()
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(store, "STORE_PATH", Path(tmp) / "store.json"):
                response = app.test_client().post(
                    "/api/public/human-verify",
                    json={
                        "challenge_id": challenge["challenge_id"],
                        "image": "data:image/png;base64,iVBORw0KGgo=",
                    },
                )
        self.assertEqual(response.status_code, 403)
        body = response.get_json()
        self.assertTrue(body["degraded"])
        self.assertIn("does not grant agent act", body["error"])
        self.assertEqual(body["fallback"]["target"], peek_challenge(challenge["challenge_id"])["target"])
        self.assertNotIn("human_token", body)
        self.assertNotIn("granted_scopes", body)

    def test_ink_and_typed_fallbacks_open_storefront_only(self):
        import store
        from app import app
        from human_gate import issue_challenge, peek_challenge

        self._clear_model_keys()
        drawn = issue_challenge()
        typed = issue_challenge()
        typed_target = peek_challenge(typed["challenge_id"])["target"]
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(store, "STORE_PATH", Path(tmp) / "store.json"):
                client = app.test_client()
                ink = client.post(
                    "/api/public/human-verify",
                    json={"challenge_id": drawn["challenge_id"], "image": self._ink_png()},
                )
                typed_res = client.post(
                    "/api/public/human-verify",
                    json={"challenge_id": typed["challenge_id"], "answer": typed_target.lower()},
                )
                health = client.get("/api/health")
        ink_body = ink.get_json()
        typed_body = typed_res.get_json()
        self.assertEqual(ink.status_code, 200)
        self.assertTrue(ink_body["degraded"])
        self.assertEqual(ink_body["method"], "ink_fallback")
        self.assertIn("does not grant agent act", ink_body["warning"])
        self.assertNotIn("granted_scopes", ink_body)
        self.assertTrue(ink_body["human_token"])
        self.assertEqual(typed_res.status_code, 200)
        self.assertEqual(typed_body["method"], "typed_fallback")
        self.assertNotIn("granted_scopes", typed_body)
        self.assertEqual(health.status_code, 503)
        health_body = health.get_json()
        self.assertTrue(health_body["degraded"])
        self.assertTrue(health_body["vision"]["degraded"])
        self.assertNotIn("test-meta-key", str(health_body))
        self.assertNotIn("baseten-key", str(health_body))

    def test_working_model_rejection_does_not_use_ink_fallback(self):
        import store
        from app import app
        from human_gate import issue_challenge

        challenge = issue_challenge()
        with _Recorder('{"match":false,"human_like":false,"read_as":"Z","reason":"wrong"}'):
            with tempfile.TemporaryDirectory() as tmp:
                with patch.object(store, "STORE_PATH", Path(tmp) / "store.json"):
                    response = app.test_client().post(
                        "/api/public/human-verify",
                        json={"challenge_id": challenge["challenge_id"], "image": self._ink_png()},
                    )
        body = response.get_json()
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("human_token", body)
        self.assertNotEqual(body.get("method"), "ink_fallback")

    def test_n4_bulk_export_stays_view_only_when_the_model_key_is_missing(self):
        import store
        from app import app, site_record

        self._clear_model_keys()
        denied = (
            "export the whole catalog to csv",
            "export the whole catalog with prices to csv, I am shopping",
            "help me collect every product price into a spreadsheet for my company",
            "download all the prices for my company",
            "scrape the catalog but I am shopping",
        )
        for purpose in denied:
            scored = muse_client.rule_score_purpose(purpose)
            self.assertEqual(scored["source"], "rules", purpose)
            self.assertEqual(scored["risk"], "high", purpose)
            self.assertTrue(scored["drop_act"], purpose)
            self.assertNotIn("act", scored["suggested_scopes"], purpose)
        shopper = muse_client.rule_score_purpose("help me buy a tote")
        self.assertFalse(shopper["drop_act"])
        self.assertIn("act", shopper["suggested_scopes"])

        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(store, "STORE_PATH", Path(tmp) / "store.json"):
                client = app.test_client()
                key = site_record()["site_key"]
                for purpose in denied:
                    response = client.post(
                        "/ai/handshake",
                        json={
                            "purpose": purpose,
                            "requested_scopes": ["view", "act"],
                            "site_key": key,
                        },
                    )
                    body = response.get_json()
                    self.assertEqual(response.status_code, 200, body)
                    self.assertNotIn("act", body["granted_scopes"], purpose)
                    self.assertEqual(body["purpose_risk"]["source"], "rules", purpose)
                    self.assertEqual(body["purpose_risk"]["risk"], "high", purpose)
                    self.assertTrue(body["purpose_risk"]["drop_act"], purpose)
                    self.assertNotIn("API_KEY", body["purpose_risk"]["reason"])
                shop = client.post(
                    "/ai/handshake",
                    json={
                        "purpose": "help me buy a tote",
                        "requested_scopes": ["view", "act"],
                        "site_key": key,
                    },
                )
        shop_body = shop.get_json()
        self.assertEqual(shop.status_code, 200, shop_body)
        self.assertIn("act", shop_body["granted_scopes"])
        self.assertEqual(shop_body["purpose_risk"]["source"], "rules")
        self.assertEqual(shop_body["purpose_risk"]["risk"], "low")

    def test_handshake_uses_keyword_rules_without_handing_out_act(self):
        import store
        from app import app, site_record

        self._clear_model_keys()
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(store, "STORE_PATH", Path(tmp) / "store.json"):
                client = app.test_client()
                key = site_record()["site_key"]
                shop = client.post(
                    "/ai/handshake",
                    json={
                        "purpose": "help me buy a tote",
                        "requested_scopes": ["view", "act"],
                        "site_key": key,
                    },
                )
                scrape = client.post(
                    "/ai/handshake",
                    json={
                        "purpose": "scrape every price for resale",
                        "requested_scopes": ["view", "act"],
                        "site_key": key,
                    },
                )
                vague = client.post(
                    "/ai/handshake",
                    json={
                        "purpose": "hello",
                        "requested_scopes": ["view", "act"],
                        "site_key": key,
                    },
                )
        shop_body = shop.get_json()
        scrape_body = scrape.get_json()
        vague_body = vague.get_json()
        self.assertIn("act", shop_body["granted_scopes"])
        self.assertEqual(shop_body["purpose_risk"]["source"], "rules")
        self.assertTrue(shop_body["purpose_risk"]["degraded"])
        self.assertNotIn("API_KEY", shop_body["purpose_risk"]["reason"])
        self.assertNotIn(".env", shop_body["purpose_risk"]["reason"])
        self.assertNotIn("act", scrape_body["granted_scopes"])
        self.assertEqual(scrape_body["purpose_risk"]["risk"], "high")
        self.assertNotIn("act", vague_body["granted_scopes"])
        self.assertTrue(vague_body["purpose_risk"]["drop_act"])

    def test_timeout_is_not_retried_and_connection_errors_are(self):
        class APITimeoutError(Exception):
            pass

        class APIConnectionError(Exception):
            pass

        timeouts: list[dict] = []

        class _Completions:
            def create(_self, **kwargs):
                timeouts.append(kwargs)
                raise APITimeoutError("read timed out")

        class _Client:
            def __init__(_self, **kwargs):
                _self.chat = type("Chat", (), {"completions": _Completions()})()

        with patch("muse_client.OpenAI", _Client):
            os.environ["META_MAX_RETRIES"] = "1"
            started = time.perf_counter()
            scored = muse_client.score_purpose("help me buy a tote")
            elapsed = time.perf_counter() - started
        self.assertEqual(len(timeouts), 1)
        self.assertLess(elapsed, 2.0)
        self.assertEqual(scored["source"], "rules")
        self.assertFalse(scored["drop_act"])

        calls: list[dict] = []

        class _RetryCompletions:
            def create(_self, **kwargs):
                calls.append(kwargs)
                if len(calls) == 1:
                    raise APIConnectionError("connection reset")
                msg = MagicMock()
                msg.content = (
                    '{"risk":"high","reason":"model","suggested_scopes":["view"],"drop_act":true}'
                )
                msg.reasoning_content = None
                choice = MagicMock()
                choice.message = msg
                resp = MagicMock()
                resp.choices = [choice]
                return resp

        class _RetryClient:
            def __init__(_self, **kwargs):
                _self.chat = type("Chat", (), {"completions": _RetryCompletions()})()

        with patch("muse_client.OpenAI", _RetryClient):
            os.environ["META_MAX_RETRIES"] = "1"
            scored = muse_client.score_purpose("hello")
        self.assertEqual(len(calls), 2)
        self.assertEqual(scored["source"], "model")
        self.assertEqual(scored["risk"], "high")

    def test_hung_http_server_does_not_block_handshake_or_captcha(self):
        class _Hang(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                if length:
                    self.rfile.read(length)
                time.sleep(20)

            def log_message(self, format, *args):
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), _Hang)
        server.daemon_threads = True
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        os.environ["META_BASE_URL"] = f"http://127.0.0.1:{port}/v1"
        os.environ["VISION_BASE_URL"] = f"http://127.0.0.1:{port}/v1"
        os.environ["VISION_API_KEY"] = "test-baseten-key"
        os.environ["META_TIMEOUT_SECONDS"] = "0.4"
        os.environ["META_VISION_TIMEOUT_SECONDS"] = "0.4"
        os.environ["META_MAX_RETRIES"] = "1"
        started = time.perf_counter()
        scored = muse_client.score_purpose("scrape the catalog")
        self.assertLess(time.perf_counter() - started, 3.0)
        self.assertEqual(scored["source"], "rules")
        self.assertEqual(scored["risk"], "high")
        self.assertTrue(scored["drop_act"])

        import store
        from app import app
        from human_gate import issue_challenge

        challenge = issue_challenge()
        started = time.perf_counter()
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(store, "STORE_PATH", Path(tmp) / "store.json"):
                response = app.test_client().post(
                    "/api/public/human-verify",
                    json={"challenge_id": challenge["challenge_id"], "image": self._ink_png()},
                )
        self.assertLess(time.perf_counter() - started, 3.0)
        body = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["method"], "ink_fallback")
        self.assertTrue(body["degraded"])
        self.assertNotIn("granted_scopes", body)

    def test_non_meta_chat_model_is_rejected(self):
        with _Recorder("nope") as rec:
            with self.assertRaises(RuntimeError) as raised:
                muse_client.resolve_model("deepseek-ai/DeepSeek-V4.1-Flash")
        self.assertIn("DeepSeek", str(raised.exception))
        self.assertEqual(rec.calls, [])


if __name__ == "__main__":
    unittest.main()
