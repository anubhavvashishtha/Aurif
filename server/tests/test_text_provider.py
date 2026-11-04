"""Mocked checks for the Meta Model API text path and the Baseten fallback.

OpenAI is patched. No live key is required, and none is printed.
"""

from __future__ import annotations

import os
import sys
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
    "META_LLM_MODEL",
    "META_PROVIDER",
    "LLM_PROVIDER",
    "LLM_FALLBACK_PROVIDER",
    "META_REASONING_EFFORT",
    "BASETEN_API_KEY",
    "BASETEN_MODEL",
    "META_TIMEOUT_SECONDS",
    "META_MAX_RETRIES",
    "VISION_API_KEY",
    "VISION_MODEL",
    "VISION_BASE_URL",
    "VISION_FALLBACK_MODEL",
)

META_BASE = "https://api.meta.ai/v1"
BASETEN_BASE = "https://inference.baseten.co/v1"
BASETEN_MODEL = "meta-models/muse-spark-open-1026"


class _StatusError(Exception):
    def __init__(self, status: int, message: str = ""):
        super().__init__(message or f"http {status}")
        self.status_code = status


class _ReadTimeout(Exception):
    """Name contains 'timeout' so the client treats it as a read timeout."""


class _Recorder:
    """One outcome per chat.completions.create call.

    An outcome is an exception, or a string (message content), or a
    (content, reasoning) pair.
    """

    def __init__(self, *outcomes: object):
        self.outcomes = list(outcomes)
        self.clients: list[dict] = []
        self.calls: list[dict] = []

    def __enter__(self):
        recorder = self

        class _Completions:
            def create(_self, **kwargs):
                recorder.calls.append(kwargs)
                index = len(recorder.calls) - 1
                outcome = recorder.outcomes[index] if index < len(recorder.outcomes) else ""
                if isinstance(outcome, BaseException):
                    raise outcome
                if isinstance(outcome, tuple):
                    content, reasoning = outcome
                else:
                    content, reasoning = outcome, None
                msg = MagicMock()
                msg.content = content
                msg.reasoning = None
                msg.reasoning_content = reasoning
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


class TextProvider(unittest.TestCase):
    def setUp(self):
        self._saved = {key: os.environ.get(key) for key in ENV_KEYS}
        self._dotenv = patch("muse_client.load_dotenv", lambda *args, **kwargs: False)
        self._dotenv.start()
        for key in ENV_KEYS:
            os.environ.pop(key, None)
        muse_client.reset_model_status()
        muse_client._ignored_llm_providers.clear()

    def tearDown(self):
        self._dotenv.stop()
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _meta_key(self, value: str = "test-meta-key") -> None:
        os.environ["META_API_KEY"] = value

    def test_unset_provider_uses_meta_model_api(self):
        self._meta_key()
        os.environ["BASETEN_API_KEY"] = "test-baseten-key"
        with _Recorder("hello") as rec:
            text = muse_client.complete(
                [{"role": "user", "content": "hi"}],
                max_tokens=2048,
                temperature=0.1,
            )
        self.assertEqual(text, "hello")
        self.assertEqual(rec.clients[0]["base_url"], META_BASE)
        self.assertEqual(rec.clients[0]["api_key"], "test-meta-key")
        self.assertEqual(rec.calls[0]["model"], "muse-spark-1.3")
        extra = rec.calls[0]["extra_body"]
        self.assertEqual(extra.get("reasoning_effort"), "low")
        self.assertNotIn("chat_template_kwargs", extra)
        self.assertNotIn("top_p", rec.calls[0])

    def test_baseten_provider_ignores_meta_key_and_overrides(self):
        self._meta_key("meta-secret")
        os.environ["BASETEN_API_KEY"] = "baseten-secret"
        os.environ["LLM_PROVIDER"] = "baseten"
        os.environ["META_BASE_URL"] = META_BASE
        os.environ["META_MODEL"] = "muse-spark-1.3"
        os.environ["META_LLM_MODEL"] = "muse-spark-1.2"
        with _Recorder("from baseten") as rec:
            muse_client.complete([{"role": "user", "content": "hi"}])
        self.assertEqual(len(rec.clients), 1)
        self.assertEqual(rec.clients[0]["base_url"], BASETEN_BASE)
        self.assertEqual(rec.clients[0]["api_key"], "baseten-secret")
        self.assertNotEqual(rec.clients[0]["api_key"], "meta-secret")
        self.assertEqual(rec.calls[0]["model"], BASETEN_MODEL)
        joined = str(rec.clients) + str(rec.calls)
        self.assertNotIn("meta-secret", joined)
        extra = rec.calls[0]["extra_body"]
        self.assertEqual(extra["reasoning_effort"], "low")
        self.assertEqual(extra["chat_template_kwargs"], {"reasoning_effort": "low"})

    def test_meta_provider_without_a_key_does_not_call(self):
        os.environ["LLM_PROVIDER"] = "meta"
        os.environ["BASETEN_API_KEY"] = "baseten-secret"
        with _Recorder("should not be used") as rec:
            scored = muse_client.score_purpose("compare tote prices")
        self.assertEqual(rec.clients, [])
        self.assertEqual(rec.calls, [])
        self.assertEqual(scored["source"], "rules")
        self.assertTrue(scored["degraded"])
        health = muse_client.health_snapshot()
        self.assertTrue(health["text"]["degraded"])
        self.assertIn("misconfigured", (health["text"]["last_error"] or "").lower())
        self.assertNotIn("baseten-secret", str(health))
        self.assertIsNone(health["text"]["fallback"])

    def test_meta_llm_model_wins_over_meta_model(self):
        self._meta_key()
        os.environ["META_MODEL"] = "muse-spark-1.0"
        os.environ["META_LLM_MODEL"] = "muse-spark-1.2"
        with _Recorder("ok") as rec:
            muse_client.complete([{"role": "user", "content": "hi"}])
        self.assertEqual(rec.calls[0]["model"], "muse-spark-1.2")
        self.assertEqual(rec.clients[0]["base_url"], META_BASE)

    def test_each_call_site_posts_to_meta(self):
        self._meta_key()
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
        events = [{"kind": "handshake", "agent_id": "shop-bot", "detail": {}}]
        jobs = [
            (
                "score_purpose",
                '{"risk":"low","reason":"shopper help","suggested_scopes":["view"],"drop_act":false}',
                lambda: muse_client.score_purpose("help a user buy a tote"),
            ),
            (
                "propose_policy",
                '{"summary":"Leave home open.","patches":[]}',
                lambda: muse_client.propose_policy("leave the home page open", endpoints),
            ),
            (
                "summarize_activity",
                '{"summary":"One event.","risks":[],"suggested_blocked_agents":[]}',
                lambda: muse_client.summarize_activity(events),
            ),
            (
                "compose_reply",
                "The price is $10.",
                lambda: muse_browse._compose_reply(
                    message="what is the price",
                    steps=[],
                    fields=[{"label": "Price", "value": "$10"}],
                    denied=False,
                ),
            ),
            (
                "page_report",
                "I can see the product name and the listed price on this page for the owner.",
                lambda: _muse_report_site_response(
                    "Name: Field Tote",
                    seen_fields=[("Name", "Field Tote")],
                ),
            ),
        ]
        for name, content, fn in jobs:
            with self.subTest(name=name):
                muse_client.reset_model_status()
                with _Recorder(content) as rec:
                    fn()
                self.assertTrue(rec.clients, name)
                self.assertEqual(rec.clients[0]["base_url"], META_BASE)
                self.assertEqual(rec.clients[0]["api_key"], "test-meta-key")
                self.assertEqual(rec.calls[0]["model"], "muse-spark-1.3")
                self.assertNotIn("top_p", rec.calls[0])
                self.assertNotIn("chat_template_kwargs", rec.calls[0].get("extra_body") or {})

    def test_meta_401_uses_keyword_rules_and_hides_the_key(self):
        self._meta_key("test-meta-key")
        err = _StatusError(401, "unauthorized test-meta-key")
        with _Recorder(err) as rec:
            with self.assertLogs("aurif.models", level="ERROR") as logs:
                scored = muse_client.score_purpose("compare tote prices")
        self.assertEqual(len(rec.clients), 1)
        self.assertEqual(len(rec.calls), 1)
        self.assertEqual(scored["source"], "rules")
        self.assertEqual(scored["fallback"], "keyword_rules")
        health = muse_client.health_snapshot()
        self.assertTrue(health["text"]["degraded"])
        self.assertFalse(health["text"]["last_ok"])
        blob = "\n".join(logs.output) + str(health) + str(scored)
        self.assertNotIn("test-meta-key", blob)
        self.assertIn("401", health["text"]["last_error"])

    def test_meta_429_is_retried_once(self):
        self._meta_key()
        err = _StatusError(429, "slow down")
        with _Recorder(err, err) as rec:
            scored = muse_client.score_purpose("buy a tote")
        self.assertEqual(len(rec.clients), 1)
        self.assertEqual(len(rec.calls), 2)
        self.assertEqual(scored["source"], "rules")

    def test_meta_read_timeout_is_not_retried(self):
        self._meta_key()
        with _Recorder(_ReadTimeout("read timed out")) as rec:
            scored = muse_client.score_purpose("buy a tote")
        self.assertEqual(len(rec.clients), 1)
        self.assertEqual(len(rec.calls), 1)
        self.assertEqual(scored["source"], "rules")

    def test_meta_400_mentioning_reasoning_effort_retries_without_it(self):
        self._meta_key()
        err = _StatusError(400, "unknown field reasoning_effort")
        with _Recorder(err, "visible answer") as rec:
            text = muse_client.complete(
                [{"role": "user", "content": "hi"}],
                max_tokens=2048,
                temperature=0.1,
            )
        self.assertEqual(text, "visible answer")
        self.assertEqual(len(rec.clients), 2)
        self.assertEqual(len(rec.calls), 2)
        self.assertEqual(rec.calls[0]["extra_body"], {"reasoning_effort": "low"})
        self.assertNotIn("reasoning_effort", rec.calls[1].get("extra_body") or {})
        self.assertNotIn("chat_template_kwargs", rec.calls[1].get("extra_body") or {})
        self.assertEqual(rec.clients[0]["base_url"], META_BASE)
        self.assertEqual(rec.clients[1]["base_url"], META_BASE)

    def test_meta_503_falls_back_to_baseten_once(self):
        self._meta_key()
        os.environ["BASETEN_API_KEY"] = "baseten-secret"
        os.environ["LLM_FALLBACK_PROVIDER"] = "baseten"
        err = _StatusError(503, "meta down")
        with _Recorder(err, err, "baseten answer") as rec:
            text = muse_client.complete([{"role": "user", "content": "hi"}])
        self.assertEqual(text, "baseten answer")
        self.assertEqual(len(rec.clients), 2)
        self.assertEqual(rec.clients[0]["base_url"], META_BASE)
        self.assertEqual(rec.clients[0]["api_key"], "test-meta-key")
        self.assertEqual(rec.clients[1]["base_url"], BASETEN_BASE)
        self.assertEqual(rec.clients[1]["api_key"], "baseten-secret")
        self.assertEqual(rec.calls[-1]["model"], BASETEN_MODEL)
        extra = rec.calls[-1]["extra_body"]
        self.assertEqual(extra["reasoning_effort"], "low")
        self.assertEqual(extra["chat_template_kwargs"], {"reasoning_effort": "low"})
        health = muse_client.health_snapshot()
        self.assertTrue(health["text"]["last_ok"])
        self.assertIn("503", health["text"]["last_error"])
        self.assertEqual(health["text"]["fallback"]["provider"], "baseten")
        self.assertEqual(health["text"]["fallback"]["model"], BASETEN_MODEL)
        self.assertTrue(health["text"]["fallback"]["label"])
        self.assertNotIn("test-meta-key", str(health))
        self.assertNotIn("baseten-secret", str(health))

    def test_meta_400_without_reasoning_effort_does_not_fall_back(self):
        self._meta_key()
        os.environ["BASETEN_API_KEY"] = "baseten-secret"
        os.environ["LLM_FALLBACK_PROVIDER"] = "baseten"
        err = _StatusError(400, "temperature and top_p were both set")
        with _Recorder(err, "should not run") as rec:
            with self.assertRaises(_StatusError):
                muse_client.complete([{"role": "user", "content": "hi"}])
        self.assertEqual(len(rec.clients), 1)
        self.assertEqual(rec.clients[0]["base_url"], META_BASE)
        self.assertEqual(len(rec.calls), 1)

    def test_reasoning_only_does_not_fall_back(self):
        self._meta_key()
        os.environ["BASETEN_API_KEY"] = "baseten-secret"
        os.environ["LLM_FALLBACK_PROVIDER"] = "Baseten"
        with _Recorder(("", "only the reasoning trace")) as rec:
            scored = muse_client.score_purpose("buy a tote")
        self.assertEqual(len(rec.clients), 1)
        self.assertEqual(rec.clients[0]["base_url"], META_BASE)
        self.assertEqual(scored["source"], "rules")
        self.assertEqual(scored["fallback"], "keyword_rules")
        self.assertTrue(scored["degraded"])

    def test_error_text_does_not_leak_a_meta_key(self):
        key = "LLM_123456_abcdefghijkl"
        self._meta_key(key)
        err = _StatusError(500, f"provider echoed {key} in the body")
        with _Recorder(err) as rec:
            with self.assertLogs("aurif.models", level="DEBUG") as logs:
                scored = muse_client.score_purpose("buy a tote")
        self.assertEqual(len(rec.calls), 2)
        blob = "\n".join(logs.output)
        health = muse_client.health_snapshot()
        providers = muse_client.api_providers()
        self.assertNotIn(key, blob)
        self.assertNotIn(key, str(health))
        self.assertNotIn(key, str(providers))
        self.assertNotIn(key, str(scored))
        self.assertEqual(muse_client._scrub_secrets(f"see {key} please"), "see [redacted] please")
        self.assertIn("[redacted]", muse_client._scrub_secrets(key))

    def test_unrecognized_provider_warns_once_and_follows_the_key(self):
        self._meta_key()
        os.environ["LLM_PROVIDER"] = "llama-api"
        with self.assertLogs("aurif.models", level="WARNING") as logs:
            with _Recorder("ok") as rec:
                muse_client.complete([{"role": "user", "content": "hi"}])
                muse_client.complete([{"role": "user", "content": "hi again"}])
        warnings = [line for line in logs.output if "LLM_PROVIDER=" in line]
        self.assertEqual(len(warnings), 1)
        self.assertIn("treating it as unset", warnings[0])
        self.assertEqual(rec.clients[0]["base_url"], META_BASE)
        self.assertEqual(rec.calls[0]["model"], "muse-spark-1.3")

    def test_startup_log_names_the_fallback_without_the_key(self):
        self._meta_key("meta-secret")
        os.environ["BASETEN_API_KEY"] = "baseten-secret"
        os.environ["LLM_FALLBACK_PROVIDER"] = "baseten"
        with self.assertLogs("aurif.models", level="INFO") as logs:
            muse_client.log_active_models()
        text = "\n".join(logs.output)
        self.assertIn("fallback_provider=baseten", text)
        self.assertIn(f"fallback_model={BASETEN_MODEL}", text)
        self.assertIn("key=set", text)
        self.assertNotIn("meta-secret", text)
        self.assertNotIn("baseten-secret", text)

    def test_meta_llm_model_does_not_replace_the_baseten_model(self):
        os.environ["BASETEN_API_KEY"] = "baseten-secret"
        os.environ["META_LLM_MODEL"] = "muse-spark-1.3"
        with _Recorder("from baseten") as rec:
            muse_client.complete([{"role": "user", "content": "hi"}])
        self.assertEqual(len(rec.clients), 1)
        self.assertEqual(rec.clients[0]["base_url"], BASETEN_BASE)
        self.assertEqual(rec.clients[0]["api_key"], "baseten-secret")
        self.assertEqual(rec.calls[0]["model"], BASETEN_MODEL)
        self.assertNotIn("muse-spark-1.3", rec.calls[0]["model"])

    def test_meta_503_without_fallback_builds_one_client(self):
        self._meta_key()
        os.environ["BASETEN_API_KEY"] = "baseten-secret"
        err = _StatusError(503, "meta down")
        with _Recorder(err, err) as rec:
            with self.assertRaises(_StatusError):
                muse_client.complete([{"role": "user", "content": "hi"}])
        self.assertEqual(len(rec.clients), 1)
        self.assertEqual(rec.clients[0]["base_url"], META_BASE)
        self.assertEqual(len(rec.calls), 2)

    def test_read_timeout_does_not_use_an_opted_in_fallback(self):
        self._meta_key()
        os.environ["BASETEN_API_KEY"] = "baseten-secret"
        os.environ["LLM_FALLBACK_PROVIDER"] = "baseten"
        with _Recorder(_ReadTimeout("read timed out"), "should not run") as rec:
            with self.assertRaises(_ReadTimeout):
                muse_client.complete([{"role": "user", "content": "hi"}])
        self.assertEqual(len(rec.clients), 1)
        self.assertEqual(rec.clients[0]["base_url"], META_BASE)
        self.assertEqual(len(rec.calls), 1)

    def test_401_and_429_with_fallback_each_use_one_baseten_client(self):
        self._meta_key()
        os.environ["BASETEN_API_KEY"] = "baseten-secret"
        os.environ["LLM_FALLBACK_PROVIDER"] = "baseten"

        unauthorized = _StatusError(401, "unauthorized")
        with _Recorder(unauthorized, "from baseten") as rec:
            text = muse_client.complete([{"role": "user", "content": "hi"}])
        self.assertEqual(text, "from baseten")
        self.assertEqual(len(rec.clients), 2)
        self.assertEqual(rec.clients[0]["base_url"], META_BASE)
        self.assertEqual(rec.clients[1]["base_url"], BASETEN_BASE)
        self.assertEqual(rec.clients[1]["api_key"], "baseten-secret")
        health = muse_client.health_snapshot()
        self.assertTrue(health["text"]["last_ok"])
        self.assertIn("401", health["text"]["last_error"])

        muse_client.reset_model_status()
        limited = _StatusError(429, "slow down")
        with _Recorder(limited, limited, "from baseten again") as rec:
            text = muse_client.complete([{"role": "user", "content": "hi"}])
        self.assertEqual(text, "from baseten again")
        baseten_clients = [row for row in rec.clients if row["base_url"] == BASETEN_BASE]
        self.assertEqual(len(baseten_clients), 1)
        self.assertEqual(len(rec.clients), 2)
        self.assertEqual(rec.clients[0]["base_url"], META_BASE)
        health = muse_client.health_snapshot()
        self.assertTrue(health["text"]["last_ok"])
        self.assertIn("429", health["text"]["last_error"])

    def test_vision_fallback_card_follows_the_vision_env(self):
        bare = muse_client.health_snapshot()
        self.assertIsNone(bare["vision"]["fallback"])
        os.environ["VISION_FALLBACK_MODEL"] = BASETEN_MODEL
        armed = muse_client.health_snapshot()
        card = armed["vision"]["fallback"]
        self.assertEqual(card["provider"], "baseten")
        self.assertEqual(card["model"], BASETEN_MODEL)
        self.assertEqual(card["label"], "Muse Spark Open")
        self.assertEqual(set(card), {"provider", "model", "label"})

    def test_api_health_keeps_status_codes_and_includes_fallback(self):
        from app import app

        client = app.test_client()
        self._meta_key()
        os.environ["VISION_API_KEY"] = "vision-key"
        os.environ["VISION_MODEL"] = "example/sam-3.1"
        os.environ["VISION_BASE_URL"] = "https://vision.example.test/v1"
        both = client.get("/api/health")
        body = both.get_json()
        self.assertEqual(both.status_code, 200)
        self.assertTrue(body["ok"])
        self.assertFalse(body["partial"])
        self.assertFalse(body["degraded"])
        self.assertIn("fallback", body["text"])
        self.assertIn("fallback", body["vision"])
        self.assertIsNone(body["text"]["fallback"])
        self.assertIsNone(body["vision"]["fallback"])

        os.environ.pop("VISION_API_KEY", None)
        muse_client.reset_model_status()
        partial = client.get("/api/health")
        body = partial.get_json()
        self.assertEqual(partial.status_code, 200)
        self.assertTrue(body["ok"])
        self.assertTrue(body["partial"])
        self.assertTrue(body["degraded"])
        self.assertFalse(body["text"]["degraded"])
        self.assertTrue(body["vision"]["degraded"])
        self.assertIn("fallback", body["text"])
        self.assertIn("fallback", body["vision"])

        os.environ.pop("META_API_KEY", None)
        os.environ.pop("MODEL_API_KEY", None)
        os.environ["VISION_API_KEY"] = "vision-key"
        muse_client.reset_model_status()
        down = client.get("/api/health")
        body = down.get_json()
        self.assertEqual(down.status_code, 503)
        self.assertFalse(body["ok"])
        self.assertFalse(body["partial"])
        self.assertTrue(body["degraded"])
        self.assertTrue(body["text"]["degraded"])
        self.assertFalse(body["vision"]["degraded"])
        self.assertIn("fallback", body["text"])
        self.assertIn("fallback", body["vision"])
        raw = down.get_data(as_text=True)
        self.assertNotIn("test-meta-key", raw)
        self.assertNotIn("vision-key", raw)

    def _handshake(self, client, purpose: str = "buy a tote"):
        import store
        from app import site_record

        return client.post(
            "/ai/handshake",
            json={
                "purpose": purpose,
                "requested_scopes": ["view", "act"],
                "site_key": site_record()["site_key"],
            },
        )

    def test_rejected_key_is_not_reported_as_missing(self):
        import tempfile

        import store
        from app import app

        rejected = "LLM_000_dummyrejectedkey"
        for status, word in ((401, "unauthorized"), (403, "forbidden")):
            with self.subTest(status=status):
                muse_client.reset_model_status()
                os.environ["META_API_KEY"] = rejected
                os.environ.pop("LLM_FALLBACK_PROVIDER", None)
                err = _StatusError(status, f"invalid_api_key: {rejected}")
                with tempfile.TemporaryDirectory() as tmp:
                    with patch.object(store, "STORE_PATH", Path(tmp) / "store.json"):
                        client = app.test_client()
                        with _Recorder(err):
                            handshake = self._handshake(client)
                        health = client.get("/api/health")
                self.assertEqual(handshake.status_code, 200)
                self.assertEqual(health.status_code, 503)
                text = health.get_json()["text"]
                self.assertTrue(text["key_configured"])
                self.assertEqual(
                    text["last_error"],
                    f"key rejected by Meta ({status} {word}), check the key",
                )
                self.assertNotIn("missing", text["last_error"])
                warning = handshake.get_json()["purpose_risk"]["warning"]
                self.assertIn("key rejected by Meta", warning)
                self.assertNotIn("missing", warning.lower())
                raw = handshake.get_data(as_text=True) + health.get_data(as_text=True)
                self.assertNotIn(rejected, raw)

    def test_missing_key_is_still_misconfigured(self):
        import tempfile

        import store
        from app import app

        for name in ("META_API_KEY", "MODEL_API_KEY", "BASETEN_API_KEY", "LLM_PROVIDER"):
            os.environ.pop(name, None)
        muse_client.reset_model_status()
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(store, "STORE_PATH", Path(tmp) / "store.json"):
                client = app.test_client()
                with _Recorder("should not be called") as rec:
                    handshake = self._handshake(client)
                health = client.get("/api/health")
        self.assertEqual(rec.clients, [])
        self.assertEqual(handshake.status_code, 200)
        self.assertEqual(health.status_code, 503)
        text = health.get_json()["text"]
        self.assertFalse(text["key_configured"])
        self.assertEqual(text["last_error"], "model key missing or provider misconfigured")
        self.assertIsNone(text["fallback_error"])

    def test_failed_text_fallback_keeps_the_primary_error(self):
        self._meta_key()
        os.environ["BASETEN_API_KEY"] = "baseten-secret"
        os.environ["LLM_FALLBACK_PROVIDER"] = "baseten"
        primary = _StatusError(401, "invalid_api_key")
        fallback = _StatusError(503, "baseten down")
        with _Recorder(primary, fallback) as rec:
            with self.assertRaises(_StatusError):
                muse_client.complete([{"role": "user", "content": "hi"}])
        self.assertEqual(len(rec.clients), 2)
        self.assertEqual(rec.clients[1]["base_url"], BASETEN_BASE)
        health = muse_client.health_snapshot()
        self.assertFalse(health["text"]["last_ok"])
        self.assertEqual(
            health["text"]["last_error"],
            "key rejected by Meta (401 unauthorized), check the key",
        )
        self.assertEqual(health["text"]["fallback_error"], "model request failed (503)")
        self.assertNotIn("baseten-secret", str(health))
        self.assertNotIn("test-meta-key", str(health))


if __name__ == "__main__":
    unittest.main()
