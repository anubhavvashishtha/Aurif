"""Vision provider selection for draw-CAPTCHA. The OpenAI client is mocked.

A Meta key selects Muse Spark 1.3. VISION_PROVIDER picks meta or baseten.
VISION_FALLBACK_PROVIDER is an opt-in Baseten retry. No test prints a key.
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

import muse_client  # noqa: E402

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
    "VISION_FALLBACK_PROVIDER",
    "BASETEN_API_KEY",
    "BASETEN_MODEL",
    "META_TIMEOUT_SECONDS",
    "META_VISION_TIMEOUT_SECONDS",
    "META_MAX_RETRIES",
)

_MATCH = '{"match":true,"human_like":true,"read_as":"A","reason":"ok"}'


def _stroke_png() -> str:
    import base64
    from io import BytesIO

    from PIL import Image, ImageDraw

    image = Image.new("L", (128, 128), 255)
    pen = ImageDraw.Draw(image)
    pen.line((16, 96, 40, 24, 64, 96, 96, 24, 112, 96), fill=0, width=4)
    buf = BytesIO()
    image.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _blank_png() -> str:
    import base64
    from io import BytesIO

    from PIL import Image

    image = Image.new("L", (128, 128), 255)
    buf = BytesIO()
    image.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _speck_png() -> str:
    import base64
    from io import BytesIO

    from PIL import Image

    image = Image.new("L", (8, 8), 255)
    image.putpixel((2, 2), 0)
    image.putpixel((3, 2), 0)
    buf = BytesIO()
    image.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


class _Recorder:
    def __init__(
        self,
        content: str,
        error: BaseException | None = None,
        *,
        reasoning: str | None = None,
    ):
        self.content = content
        self.error = error
        self.reasoning = reasoning
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


class VisionProviderSelection(unittest.TestCase):
    def setUp(self):
        self._saved = {key: os.environ.get(key) for key in ENV_KEYS}
        self._dotenv = patch("muse_client.load_dotenv", lambda *args, **kwargs: False)
        self._dotenv.start()
        for key in ENV_KEYS:
            os.environ.pop(key, None)
        muse_client.reset_model_status()

    def tearDown(self):
        self._dotenv.stop()
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_meta_key_selects_meta_vision_when_provider_is_unset(self):
        secret = "LLM_100_primary"
        os.environ["META_API_KEY"] = secret
        os.environ["BASETEN_API_KEY"] = "baseten-key"
        os.environ["VISION_FALLBACK_PROVIDER"] = "baseten"
        image = _stroke_png()
        with _Recorder(_MATCH) as rec:
            with self.assertLogs("aurif.models", level="INFO") as logs:
                muse_client.log_active_models()
            verdict = muse_client.verify_drawing(image, "A")
        self.assertEqual(len(rec.clients), 1)
        self.assertEqual(rec.clients[0]["base_url"], "https://api.meta.ai/v1")
        self.assertEqual(rec.clients[0]["api_key"], secret)
        self.assertEqual(rec.calls[0]["model"], "muse-spark-1.3")
        self.assertEqual(rec.calls[0]["temperature"], 0.1)
        self.assertEqual(rec.calls[0]["max_tokens"], 2048)
        self.assertEqual(rec.calls[0]["extra_body"], {"reasoning_effort": "low"})
        self.assertNotIn("top_p", rec.calls[0])
        user = rec.calls[0]["messages"][1]["content"]
        self.assertEqual(user[0]["type"], "text")
        self.assertEqual(user[1]["type"], "image_url")
        self.assertEqual(user[1]["image_url"]["url"], image)
        self.assertIsInstance(rec.calls[0]["messages"][0]["content"], str)
        self.assertEqual(verdict["provider"], "meta")
        self.assertEqual(verdict["powered_by"], "Meta Muse Spark 1.3")
        self.assertTrue(verdict["ok"])
        health = muse_client.health_snapshot()
        self.assertEqual(health["vision"]["provider"], "meta")
        self.assertEqual(health["vision"]["model"], "muse-spark-1.3")
        logged = "\n".join(logs.output)
        vision_line = next(line for line in logs.output if "Aurif vision model:" in line)
        self.assertIn("provider=meta", vision_line)
        self.assertIn("model=muse-spark-1.3", vision_line)
        self.assertIn("key=set", vision_line)
        self.assertIn("fallback_provider=baseten", vision_line)
        self.assertIn("fallback_model=meta-models/muse-spark-open-1026", vision_line)
        self.assertNotIn(secret, logged)
        self.assertNotIn(secret, str(verdict))
        self.assertNotIn(secret, str(health))
        self.assertNotIn("baseten-key", logged)

    def test_baseten_provider_ignores_meta_key(self):
        secret = "LLM_300_meta"
        os.environ["META_API_KEY"] = secret
        os.environ["BASETEN_API_KEY"] = "baseten-key"
        os.environ["VISION_PROVIDER"] = "Baseten"
        with _Recorder(_MATCH) as rec:
            verdict = muse_client.verify_drawing(_stroke_png(), "A")
        self.assertEqual(rec.clients[0]["base_url"], "https://inference.baseten.co/v1")
        self.assertEqual(rec.clients[0]["api_key"], "baseten-key")
        self.assertEqual(rec.calls[0]["model"], "meta-models/muse-spark-open-1026")
        self.assertEqual(verdict["provider"], "baseten")
        self.assertEqual(verdict["powered_by"], "Meta Muse Spark Open")
        self.assertNotEqual(rec.clients[0]["api_key"], secret)

    def test_meta_provider_without_a_key_makes_no_call_and_text_stays_up(self):
        os.environ["VISION_PROVIDER"] = "meta"
        os.environ["BASETEN_API_KEY"] = "baseten-text-key"
        image = _stroke_png()
        with _Recorder(_MATCH) as rec:
            verdict = muse_client.verify_drawing(image, "A")
        self.assertEqual(rec.clients, [])
        self.assertEqual(rec.calls, [])
        self.assertFalse(verdict["ok"])
        self.assertTrue(verdict["unavailable"])
        self.assertIn("vision provider misconfigured", verdict["reason"])
        self.assertIn("META_API_KEY", verdict["reason"])
        self.assertIn("VISION_PROVIDER", verdict["reason"])
        with _Recorder(
            '{"risk":"low","reason":"ok","suggested_scopes":["view"],"drop_act":false}'
        ) as text_rec:
            scored = muse_client.score_purpose("help me buy a tote")
        self.assertEqual(scored["source"], "model")
        self.assertEqual(text_rec.clients[0]["base_url"], "https://inference.baseten.co/v1")
        self.assertEqual(text_rec.clients[0]["api_key"], "baseten-text-key")
        self.assertEqual(text_rec.calls[0]["model"], "meta-models/muse-spark-open-1026")
        from app import app

        response = app.test_client().get("/api/health")
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertTrue(body["partial"])
        self.assertTrue(body["vision"]["degraded"])
        self.assertEqual(body["vision"]["provider"], "meta")
        self.assertFalse(body["text"]["degraded"])
        self.assertTrue(body["text"]["last_ok"])
        self.assertNotIn("baseten-text-key", response.get_data(as_text=True))

    def test_meta_vision_model_overrides_the_spark_default(self):
        os.environ["META_API_KEY"] = "LLM_500_meta"
        os.environ["META_VISION_MODEL"] = "muse-spark-1.2"
        os.environ["VISION_MODEL"] = "openai/gpt-4o"
        with _Recorder(_MATCH) as rec:
            verdict = muse_client.verify_drawing(_stroke_png(), "A")
        self.assertEqual(rec.calls[0]["model"], "muse-spark-1.2")
        self.assertEqual(rec.clients[0]["base_url"], "https://api.meta.ai/v1")
        self.assertEqual(verdict["model"], "muse-spark-1.2")
        self.assertEqual(verdict["provider"], "meta")
        self.assertEqual(verdict["powered_by"], "Meta Muse Spark 1.2")

    def test_explicit_vision_base_url_beats_the_meta_default(self):
        secret = "LLM_600_meta"
        os.environ["META_API_KEY"] = secret
        os.environ["VISION_BASE_URL"] = "https://vision.example.test/v1"
        os.environ["VISION_MODEL"] = "meta-llama/Llama-4-Scout"
        os.environ["VISION_API_KEY"] = "vision-key"
        with _Recorder(_MATCH) as rec:
            verdict = muse_client.verify_drawing(_stroke_png(), "A")
        self.assertEqual(len(rec.clients), 1)
        self.assertEqual(rec.clients[0]["base_url"], "https://vision.example.test/v1")
        self.assertEqual(rec.clients[0]["api_key"], "vision-key")
        self.assertEqual(rec.calls[0]["model"], "meta-llama/Llama-4-Scout")
        self.assertEqual(verdict["model"], "meta-llama/Llama-4-Scout")
        self.assertNotEqual(verdict["provider"], "meta")
        self.assertNotIn(secret, rec.clients[0]["api_key"])
        self.assertNotIn("api.meta.ai", rec.clients[0]["base_url"])

    def test_meta_403_names_the_model_api_and_hides_the_key(self):
        secret = "LLM_4242_do_not_leak"

        class Forbidden(Exception):
            status_code = 403

            def __str__(self) -> str:
                return f"please check the api-key you provided {secret}"

        os.environ["META_API_KEY"] = secret
        from app import app

        with _Recorder("", error=Forbidden()) as rec:
            with self.assertLogs("aurif.models", level="ERROR") as logs:
                verdict = muse_client.verify_drawing(_stroke_png(), "K7")
        self.assertTrue(verdict["unavailable"])
        self.assertEqual(
            verdict["reason"],
            "vision model muse-spark-1.3: 403 forbidden, "
            "check Meta Model API model access or slug",
        )
        self.assertNotIn(secret, verdict["reason"])
        self.assertNotIn("K7", verdict["reason"])
        self.assertEqual(len(rec.clients), 1)
        logged = "\n".join(logs.output)
        self.assertIn("403 forbidden", logged)
        self.assertNotIn(secret, logged)
        health = muse_client.health_snapshot()
        self.assertEqual(health["vision"]["last_error"], verdict["reason"])
        self.assertNotIn(secret, str(health))
        client = app.test_client()
        health_body = client.get("/api/health").get_data(as_text=True)
        models_body = client.get("/api/ai/models").get_data(as_text=True)
        self.assertNotIn(secret, health_body)
        self.assertNotIn(secret, models_body)
        self.assertNotIn(secret, logged)

    def test_meta_503_falls_back_to_baseten_and_a_read_timeout_does_not(self):
        secret = "LLM_800_meta"
        os.environ["META_API_KEY"] = secret
        os.environ["VISION_FALLBACK_PROVIDER"] = "baseten"
        os.environ["BASETEN_API_KEY"] = "baseten-key"

        class ServerError(Exception):
            status_code = 503

        class APITimeoutError(Exception):
            def __str__(self) -> str:
                return "read timed out"

        clients: list[dict] = []
        calls: list[dict] = []

        class _Completions:
            def __init__(self, index: int):
                self.index = index

            def create(self, **kwargs):
                calls.append(kwargs)
                if self.index == 1:
                    raise ServerError("upstream unavailable")
                msg = MagicMock()
                msg.content = _MATCH
                msg.reasoning = None
                msg.reasoning_content = None
                choice = MagicMock()
                choice.message = msg
                resp = MagicMock()
                resp.choices = [choice]
                return resp

        class _Client:
            def __init__(self, **kwargs):
                clients.append(kwargs)
                self.chat = type("Chat", (), {"completions": _Completions(len(clients))})()

        with patch("muse_client.OpenAI", _Client):
            verdict = muse_client.verify_drawing(_stroke_png(), "A")
        self.assertEqual(len(clients), 2)
        self.assertEqual(clients[0]["base_url"], "https://api.meta.ai/v1")
        self.assertEqual(clients[0]["api_key"], secret)
        self.assertEqual(clients[1]["base_url"], "https://inference.baseten.co/v1")
        self.assertEqual(clients[1]["api_key"], "baseten-key")
        self.assertEqual(verdict["provider"], "baseten")
        self.assertTrue(verdict["ok"])
        self.assertEqual(verdict["model"], "meta-models/muse-spark-open-1026")
        health = muse_client.health_snapshot()
        self.assertTrue(health["vision"]["last_ok"])
        self.assertEqual(health["vision"]["last_error"], "model request failed (503)")
        self.assertNotIn(secret, str(verdict))
        self.assertNotIn(secret, str(health))
        self.assertNotIn("baseten-key", str(health))

        muse_client.reset_model_status()
        timeout_clients: list[dict] = []

        class _TimeoutCompletions:
            def create(self, **kwargs):
                raise APITimeoutError()

        class _TimeoutClient:
            def __init__(self, **kwargs):
                timeout_clients.append(kwargs)
                self.chat = type("Chat", (), {"completions": _TimeoutCompletions()})()

        with patch("muse_client.OpenAI", _TimeoutClient):
            timed = muse_client.verify_drawing(_stroke_png(), "A")
        self.assertEqual(len(timeout_clients), 1)
        self.assertEqual(timeout_clients[0]["base_url"], "https://api.meta.ai/v1")
        self.assertTrue(timed["unavailable"])
        self.assertEqual(timed["provider"], "meta")
        self.assertEqual(timed["reason"], "model timed out")
        self.assertNotIn(secret, str(timed))

    def test_tiny_speck_fails_a_positive_meta_match(self):
        os.environ["META_API_KEY"] = "LLM_900_meta"
        with _Recorder(_MATCH) as rec:
            verdict = muse_client.verify_drawing(_speck_png(), "A")
        self.assertEqual(rec.clients, [])
        self.assertEqual(rec.calls, [])
        self.assertFalse(verdict["ok"])
        self.assertFalse(verdict["unavailable"])
        self.assertEqual(verdict["reason"], "drawing too small")
        self.assertEqual(verdict["provider"], "meta")

    def test_blank_and_speck_make_no_model_call_from_verify_or_the_endpoint(self):
        import tempfile

        import store
        from app import app
        from human_gate import issue_challenge

        os.environ["META_API_KEY"] = "LLM_1850_meta"
        with _Recorder(_MATCH) as rec:
            blank = muse_client.verify_drawing(_blank_png(), "A")
            speck = muse_client.verify_drawing(_speck_png(), "A")
        self.assertEqual(rec.clients, [])
        self.assertEqual(rec.calls, [])
        self.assertFalse(blank["ok"])
        self.assertFalse(blank.get("unavailable"))
        self.assertEqual(blank["reason"], "blank")
        self.assertFalse(speck["ok"])
        self.assertFalse(speck.get("unavailable"))
        self.assertEqual(speck["reason"], "drawing too small")
        self.assertNotIn("LLM_1850_meta", str(blank))
        self.assertNotIn("LLM_1850_meta", str(speck))

        with _Recorder(_MATCH) as rec:
            with tempfile.TemporaryDirectory() as tmp:
                with patch.object(store, "STORE_PATH", Path(tmp) / "store.json"):
                    client = app.test_client()
                    blank_id = issue_challenge()["challenge_id"]
                    speck_id = issue_challenge()["challenge_id"]
                    blank_res = client.post(
                        "/api/public/human-verify",
                        json={"challenge_id": blank_id, "image": _blank_png()},
                    )
                    speck_res = client.post(
                        "/api/public/human-verify",
                        json={"challenge_id": speck_id, "image": _speck_png()},
                    )
        self.assertEqual(rec.clients, [])
        self.assertEqual(rec.calls, [])
        for response, reason in ((blank_res, "blank"), (speck_res, "drawing too small")):
            body = response.get_json()
            self.assertEqual(response.status_code, 403, reason)
            self.assertEqual(body["error"], "drawing did not match")
            self.assertFalse(body["verdict"]["match"])
            self.assertNotEqual(body.get("method"), "ink_fallback")
            self.assertNotIn("human_token", body)
            self.assertNotIn("LLM_1850_meta", str(body))

    def test_reasoning_content_without_a_verdict_is_unreadable_and_does_not_fall_back(self):
        os.environ["META_API_KEY"] = "LLM_1000_meta"
        os.environ["BASETEN_API_KEY"] = "baseten-key"
        os.environ["VISION_FALLBACK_PROVIDER"] = "baseten"
        with _Recorder("", reasoning="REASONING_ONLY_NOT_A_VERDICT") as rec:
            verdict = muse_client.verify_drawing(_stroke_png(), "A")
        self.assertEqual(len(rec.clients), 1)
        self.assertEqual(rec.clients[0]["base_url"], "https://api.meta.ai/v1")
        self.assertTrue(verdict["unavailable"])
        self.assertIn("unreadable", verdict["reason"])
        self.assertNotIn("REASONING_ONLY_NOT_A_VERDICT", str(verdict))
        self.assertEqual(verdict["provider"], "meta")

    def test_undecodable_image_is_rejected_before_the_meta_call(self):
        os.environ["META_API_KEY"] = "LLM_1100_meta"
        with _Recorder(_MATCH) as rec:
            verdict = muse_client.verify_drawing("data:image/png;base64,iVBORw0KGgo=", "A")
        self.assertEqual(rec.clients, [])
        self.assertEqual(rec.calls, [])
        self.assertFalse(verdict["ok"])
        self.assertFalse(verdict.get("unavailable"))
        self.assertEqual(verdict["reason"], "undecodable image")
        self.assertEqual(verdict["provider"], "meta")

    def test_meta_retries_once_when_reasoning_effort_is_rejected(self):
        class BadRequest(Exception):
            status_code = 400

            def __str__(self) -> str:
                return "unknown parameter reasoning_effort"

        calls: list[dict] = []
        clients: list[dict] = []

        class _Completions:
            def create(_self, **kwargs):
                calls.append(kwargs)
                if kwargs.get("extra_body"):
                    raise BadRequest()
                msg = MagicMock()
                msg.content = _MATCH
                msg.reasoning = None
                msg.reasoning_content = None
                choice = MagicMock()
                choice.message = msg
                resp = MagicMock()
                resp.choices = [choice]
                return resp

        class _Client:
            def __init__(_self, **kwargs):
                clients.append(kwargs)
                _self.chat = type("Chat", (), {"completions": _Completions()})()

        ticks = iter((1000.0, 1000.0, 1006.0))
        os.environ["META_API_KEY"] = "LLM_1200_meta"
        with patch("muse_client.OpenAI", _Client), patch(
            "muse_client.time.perf_counter", lambda: next(ticks)
        ):
            verdict = muse_client.verify_drawing(_stroke_png(), "A")
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(clients), 2)
        self.assertEqual(clients[0]["timeout"], 15.0)
        self.assertAlmostEqual(clients[1]["timeout"], 9.0)
        self.assertEqual(calls[0]["extra_body"], {"reasoning_effort": "low"})
        self.assertNotIn("extra_body", calls[1])
        self.assertNotIn("top_p", calls[0])
        self.assertNotIn("top_p", calls[1])
        self.assertTrue(verdict["ok"])
        self.assertEqual(verdict["provider"], "meta")

    def test_valid_non_match_does_not_use_the_provider_fallback(self):
        os.environ["META_API_KEY"] = "LLM_1400_meta"
        os.environ["VISION_FALLBACK_PROVIDER"] = "baseten"
        os.environ["BASETEN_API_KEY"] = "baseten-key"
        denied = '{"match":false,"human_like":true,"read_as":"B","reason":"wrong object"}'
        with _Recorder(denied) as rec:
            verdict = muse_client.verify_drawing(_stroke_png(), "A")
        self.assertEqual(len(rec.clients), 1)
        self.assertFalse(verdict["ok"])
        self.assertFalse(verdict["unavailable"])
        self.assertEqual(verdict["provider"], "meta")

    def test_meta_key_never_reaches_a_non_meta_host(self):
        secret = "LLM_1500_meta"
        os.environ["META_API_KEY"] = secret
        os.environ["MODEL_API_KEY"] = secret
        os.environ["BASETEN_API_KEY"] = "baseten-key"
        os.environ["VISION_BASE_URL"] = "https://vision.example.test/v1"
        os.environ["VISION_MODEL"] = "muse-spark-1.3"
        with _Recorder(_MATCH) as rec:
            verdict = muse_client.verify_drawing(_stroke_png(), "A")
        self.assertEqual(len(rec.clients), 1)
        self.assertEqual(rec.clients[0]["base_url"], "https://vision.example.test/v1")
        self.assertEqual(rec.clients[0]["api_key"], "baseten-key")
        self.assertNotIn(secret, rec.clients[0]["api_key"])
        self.assertNotIn(secret, str(rec.calls))
        self.assertNotIn(secret, str(verdict))
        self.assertNotIn("api.meta.ai", rec.clients[0]["base_url"])

        os.environ.pop("BASETEN_API_KEY", None)
        with _Recorder(_MATCH) as rec:
            missing = muse_client.verify_drawing(_stroke_png(), "A")
        self.assertEqual(rec.clients, [])
        self.assertTrue(missing["unavailable"])
        self.assertNotIn(secret, str(missing))

    def test_implicit_meta_default_uses_the_meta_key_not_vision_api_key(self):
        secret = "LLM_1600_meta"
        os.environ["META_API_KEY"] = secret
        os.environ["VISION_API_KEY"] = "old-baseten-vision-key"
        with _Recorder(_MATCH) as rec:
            verdict = muse_client.verify_drawing(_stroke_png(), "A")
        self.assertEqual(rec.clients[0]["base_url"], "https://api.meta.ai/v1")
        self.assertEqual(rec.clients[0]["api_key"], secret)
        self.assertEqual(verdict["provider"], "meta")
        self.assertNotIn("old-baseten-vision-key", str(verdict))

        os.environ["VISION_PROVIDER"] = "meta"
        with _Recorder(_MATCH) as explicit:
            muse_client.verify_drawing(_stroke_png(), "A")
        self.assertEqual(explicit.clients[0]["api_key"], "old-baseten-vision-key")
        self.assertNotEqual(explicit.clients[0]["api_key"], secret)

    def test_meta_rejects_bmp_and_accepts_jpeg(self):
        import base64
        from io import BytesIO

        from PIL import Image, ImageDraw

        os.environ["META_API_KEY"] = "LLM_1700_meta"
        with _Recorder(_MATCH) as rec:
            rejected = muse_client.verify_drawing("data:image/bmp;base64,Qk0=", "A")
        self.assertEqual(rec.clients, [])
        self.assertEqual(rec.calls, [])
        self.assertFalse(rejected["ok"])
        self.assertFalse(rejected.get("unavailable"))
        self.assertEqual(rejected["reason"], "unsupported image type")

        image = Image.new("RGB", (128, 128), "white")
        ImageDraw.Draw(image).line((16, 96, 40, 24, 64, 96, 96, 24, 112, 96), fill="black", width=4)
        buf = BytesIO()
        image.save(buf, format="JPEG")
        jpeg = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
        with _Recorder(_MATCH) as rec:
            verdict = muse_client.verify_drawing(jpeg, "A")
        self.assertEqual(len(rec.clients), 1)
        self.assertEqual(rec.clients[0]["base_url"], "https://api.meta.ai/v1")
        self.assertTrue(verdict["ok"])

    def test_lookalike_meta_urls_do_not_receive_the_meta_key(self):
        secret = "LLM_1900_meta"
        os.environ["META_API_KEY"] = secret
        os.environ["MODEL_API_KEY"] = secret
        os.environ["BASETEN_API_KEY"] = "baseten-key"
        os.environ["VISION_MODEL"] = "muse-spark-1.3"
        tricks = (
            "http://x.example/api.meta.ai/v1",
            "https://api.meta.ai.evil.tld/v1",
            "https://api.meta.ai@evil.tld/v1",
        )
        image = _stroke_png()
        for url in tricks:
            os.environ["VISION_BASE_URL"] = url
            self.assertFalse(muse_client._is_meta_model_api(url), url)
            with _Recorder(_MATCH) as rec:
                verdict = muse_client.verify_drawing(image, "A")
            self.assertEqual(len(rec.clients), 1, url)
            self.assertEqual(rec.clients[0]["base_url"], url)
            self.assertEqual(rec.clients[0]["api_key"], "baseten-key")
            self.assertNotIn(secret, rec.clients[0]["api_key"])
            self.assertNotIn(secret, str(rec.calls))
            self.assertNotIn(secret, str(verdict))
        self.assertTrue(muse_client._is_meta_model_api("https://api.meta.ai/v1"))


if __name__ == "__main__":
    unittest.main()
