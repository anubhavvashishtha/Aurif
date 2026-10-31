"""Model client for Aurif product AI features.

Text (handshake risk, policy co-pilot, activity summaries, Muse chat) stays on
a Meta model: Muse Spark 1.3 on the Meta Model API, or Muse Spark Open on
Baseten when only BASETEN_API_KEY is set.

Draw-CAPTCHA vision is separate. It defaults to DeepSeek V4.1 Flash on
Baseten's OpenAI-compatible endpoint and uses BASETEN_API_KEY. VISION_* (and
the older META_VISION_* names, when the matching VISION_* var is unset) can
point that call at another host later. Modal is not used. A non-Meta id is
refused for text only.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
# Fill missing vars from repo-root .env. Do not override existing process env
# (tests and exported keys win). A restarted Flask process picks up .env edits.
load_dotenv(ROOT / ".env", override=False)

# First-party Meta Model API. Muse Spark 1.3 reads text and images.
META_API_DEFAULT_BASE = "https://api.meta.ai/v1"
META_DEFAULT_MODEL = "muse-spark-1.3"

# Existing demo setup. Muse Spark Open on Baseten is a Meta model, and the
# draw-CAPTCHA path already sent images to this id when Modal was down.
BASETEN_BASE_URL = "https://inference.baseten.co/v1"
BASETEN_DEFAULT_MODEL = "meta-models/muse-spark-open-1026"

# Draw-CAPTCHA only. Text never reads these defaults.
VISION_DEFAULT_MODEL = "deepseek-ai/DeepSeek-V4.1-Flash-1017"
VISION_DEFAULT_BASE_URL = BASETEN_BASE_URL

log = logging.getLogger("aurif.models")

# Text calls should fail in a few seconds. Vision gets a little longer for image upload.
# Retries are extra attempts after the first, and read timeouts are not retried.
_DEFAULT_TEXT_TIMEOUT = 8.0
_DEFAULT_VISION_TIMEOUT = 15.0
_DEFAULT_MAX_RETRIES = 1

_HIGH_RISK = re.compile(
    r"\b(scrape|scraping|harvest|harvesting|resale|resell|reseller|competitor|competitors|bypass|exfil|dump|crawl|crawler|bulk)\b",
    re.I,
)
_SHOPPER = re.compile(
    r"\b(buy|purchase|shop|shopping|cart|checkout|browse|order|help|find|add|product|customer)\b",
    re.I,
)

# kind -> last call outcome. None means this process has not called the model yet.
_model_status: dict[str, dict[str, Any]] = {
    "text": {"ok": None, "error": None, "checked_at": None},
    "vision": {"ok": None, "error": None, "checked_at": None},
}

# Families we will not call. Llama and Muse ids are Meta models and are allowed
# even when the name also contains another token (for example a gateway prefix).
_NON_META_MODEL = re.compile(
    r"(deepseek|gpt-|o1-|o3-|o4-|claude|gemini|qwen|kimi|moonshot|\bglm-|mixtral|\bgrok\b)",
    re.I,
)
_META_MODEL_OK = re.compile(r"(muse|llama|meta-models|meta-llama)", re.I)


def _refresh_env() -> None:
    load_dotenv(ROOT / ".env", override=False)


def _first_env(*names: str) -> str:
    for name in names:
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return ""


def text_settings() -> dict[str, str]:
    """Resolved text-model endpoint. Read on each call so env edits apply.

    META_API_KEY / MODEL_API_KEY select the Meta Model API. When neither is
    set, BASETEN_API_KEY keeps the previous Muse Spark Open deployment.
    """
    _refresh_env()
    meta_key = _first_env("META_API_KEY", "MODEL_API_KEY")
    baseten_key = _first_env("BASETEN_API_KEY")
    using_baseten = not meta_key and bool(baseten_key)

    if _first_env("META_BASE_URL"):
        base_url = _first_env("META_BASE_URL").rstrip("/")
    elif using_baseten:
        base_url = BASETEN_BASE_URL
    else:
        base_url = META_API_DEFAULT_BASE

    if _first_env("META_MODEL"):
        model = _first_env("META_MODEL")
    elif using_baseten:
        model = _first_env("BASETEN_MODEL") or BASETEN_DEFAULT_MODEL
    else:
        model = META_DEFAULT_MODEL

    if _first_env("META_PROVIDER"):
        provider = _first_env("META_PROVIDER")
    elif using_baseten or "inference.baseten.co" in base_url:
        provider = "baseten"
    else:
        provider = "meta"

    return {
        "provider": provider,
        "base_url": base_url,
        "model": model,
        "api_key": meta_key or baseten_key,
    }


def vision_settings() -> dict[str, str]:
    """Draw-CAPTCHA endpoint. Does not inherit the text model.

    VISION_MODEL / VISION_BASE_URL / VISION_API_KEY / VISION_PROVIDER are the
    canonical knobs. Each META_VISION_* var still applies when the matching
    VISION_* var is unset, so an existing vision override keeps working.
    The default is DeepSeek on Baseten, authenticated with BASETEN_API_KEY.
    """
    _refresh_env()
    model = _first_env("VISION_MODEL", "META_VISION_MODEL") or VISION_DEFAULT_MODEL
    base_url = (
        _first_env("VISION_BASE_URL", "META_VISION_BASE_URL") or VISION_DEFAULT_BASE_URL
    ).rstrip("/")
    provider = _first_env("VISION_PROVIDER", "META_VISION_PROVIDER") or _infer_vision_provider(base_url)
    # A DeepSeek (or other non-Meta) id must not be labelled as Meta, even if
    # someone set VISION_PROVIDER=meta by mistake.
    if _model_family(model) != "meta" and provider.lower() == "meta":
        provider = _infer_vision_provider(base_url)
    return {
        "provider": provider,
        "base_url": base_url,
        "model": model,
        "api_key": _vision_api_key(base_url, model),
    }


def _infer_vision_provider(base_url: str) -> str:
    host = (base_url or "").lower()
    if "baseten" in host:
        return "baseten"
    if "api.meta.ai" in host:
        return "meta"
    if "modal" in host:
        return "modal"
    return "openai-compatible"


def _vision_api_key(base_url: str, model: str) -> str:
    """Key for the vision host. Explicit vision keys win, then a host default.

    Baseten (the default) uses BASETEN_API_KEY. The Meta Model API uses the
    Meta key so the owner can point vision back at Muse without a new secret.
    Any other host still defaults to BASETEN_API_KEY until VISION_API_KEY is set.
    """
    explicit = _first_env("VISION_API_KEY", "META_VISION_API_KEY")
    if explicit:
        return explicit
    host = (base_url or "").lower()
    if "api.meta.ai" in host or (_model_family(model) == "meta" and "baseten" not in host):
        return _first_env("META_API_KEY", "MODEL_API_KEY", "BASETEN_API_KEY")
    return _first_env("BASETEN_API_KEY")


def public_settings(cfg: dict[str, str]) -> dict[str, str]:
    """Settings safe to return from an API (no key)."""
    card = _public_card(cfg)
    return {
        "provider": cfg.get("provider") or "",
        "base_url": cfg.get("base_url") or "",
        "model": cfg.get("model") or "",
        "label": card["label"],
        "family": card["family"],
        "powered_by": card["powered_by"],
    }


def text_model_id() -> str:
    return text_settings()["model"]


def model_card() -> dict[str, str]:
    """Configured text model, safe to show in the dashboard. No API key."""
    return _public_card(text_settings())


def vision_model_card() -> dict[str, str]:
    """Configured vision model. DeepSeek is never labelled as Meta."""
    return _public_card(vision_settings())


def _stamp_call(result: dict[str, Any], *, started: float, card: dict[str, str]) -> dict[str, Any]:
    out = dict(result)
    out["model"] = card
    out["latency_ms"] = max(0, int(round((time.perf_counter() - started) * 1000)))
    return out


def _owner_warning(kind: str, exc: BaseException | None = None) -> str:
    """Dashboard copy when the Meta call did not produce the result. No secrets."""
    detail = _public_model_error(exc) if exc else "model request failed"
    if kind == "policy":
        return (
            f"Meta model unavailable ({detail}). "
            "This proposal is a keyword-rules fallback and is not applied until you confirm."
        )
    if kind == "activity":
        return (
            f"Meta model unavailable ({detail}). Showing the counted activity fallback."
        )
    return f"Meta model unavailable ({detail}). This score is the keyword-rules fallback."


def _looks_non_meta(model: str) -> bool:
    if _META_MODEL_OK.search(model or ""):
        return False
    return bool(_NON_META_MODEL.search(model or ""))


def _reject_non_meta_target(model: str, base_url: str, *, kind: str) -> None:
    """Raise if this call would hit DeepSeek or another non-Meta model."""
    blob = f"{model} {base_url}"
    if "deepseek" in blob.lower():
        raise RuntimeError(
            f"{kind} provider misconfigured: refusing DeepSeek target "
            f"({model} @ {base_url}). Set META_MODEL / META_VISION_MODEL and "
            "META_BASE_URL / META_VISION_BASE_URL to a Meta model "
            f"(default {META_DEFAULT_MODEL} at {META_API_DEFAULT_BASE})."
        )
    if _looks_non_meta(model):
        raise RuntimeError(
            f"{kind} provider misconfigured: {model!r} is not a Meta model. "
            "Use a Muse Spark or Llama model "
            f"(default {META_DEFAULT_MODEL})."
        )


def _is_meta_model_api(base_url: str) -> bool:
    return "api.meta.ai" in (base_url or "").lower()


def _output_tokens(requested: int, base_url: str) -> int:
    # Muse Spark spends output tokens on reasoning before the visible answer.
    # Tiny budgets (the browse phrasing call asks for ~60) come back empty.
    if _is_meta_model_api(base_url):
        return max(int(requested), 768)
    return int(requested)


def _meta_extra(base_url: str) -> dict[str, Any]:
    if not _is_meta_model_api(base_url):
        return {}
    effort = (_first_env("META_REASONING_EFFORT") or "low").lower()
    if effort in ("", "default", "unset"):
        return {}
    # Muse Spark rejects reasoning_effort=none with HTTP 400.
    if effort == "none":
        effort = "low"
    return {"reasoning_effort": effort}


def _model_family(model_id: str) -> str:
    """meta, deepseek, or other. Used so labels never call DeepSeek a Meta model."""
    mid = model_id or ""
    if "deepseek" in mid.lower():
        return "deepseek"
    if _META_MODEL_OK.search(mid):
        return "meta"
    return "other"


def _model_label(model_id: str) -> str:
    tail = (model_id or "").split("/")[-1]
    if "muse-spark-open" in model_id:
        return "Muse Spark Open"
    if tail.startswith("muse-spark"):
        rest = tail.removeprefix("muse-spark").lstrip("-")
        return f"Muse Spark {rest}".strip() if rest else "Muse Spark"
    return tail or model_id


def _public_model_label(model_id: str) -> str:
    mid = model_id or ""
    low = mid.lower()
    if "deepseek" in low and "flash" in low:
        return "DeepSeek V4.1 Flash"
    if "deepseek" in low:
        tail = mid.split("/")[-1]
        return tail or "DeepSeek"
    return _model_label(mid)


def _public_card(cfg: dict[str, str]) -> dict[str, str]:
    """Safe model card. `powered_by` already includes "Meta" only for Meta models."""
    model = cfg.get("model") or ""
    family = _model_family(model)
    label = _public_model_label(model)
    powered = f"Meta {label}" if family == "meta" else label
    return {
        "id": model,
        "provider": cfg.get("provider") or "",
        "label": label,
        "family": family,
        "powered_by": powered,
    }


def _vision_identity(cfg: dict[str, str]) -> dict[str, str]:
    card = _public_card(cfg)
    return {
        "model": card["id"],
        "provider": card["provider"],
        "label": card["label"],
        "family": card["family"],
        "powered_by": card["powered_by"],
    }


def log_active_models(*, echo: bool = False) -> None:
    """Log the text and vision provider/model. Never includes the API key."""
    lines: list[str] = []
    for kind, loader in (("text", text_settings), ("vision", vision_settings)):
        cfg = loader()
        try:
            # Non-Meta ids are refused for text only. Vision may be DeepSeek.
            if kind != "vision":
                _reject_non_meta_target(cfg["model"], cfg["base_url"], kind=kind)
            card = _public_card(cfg)
            line = (
                f"Aurif {kind} model: provider={cfg['provider']} "
                f"model={cfg['model']} label={card['label']} family={card['family']} "
                f"base_url={cfg['base_url']} "
                f"key={'set' if cfg.get('api_key') else 'missing'}"
            )
            log.info(line)
        except RuntimeError as exc:
            line = f"Aurif {kind} model: {exc}"
            log.error(line)
        lines.append(line)
    if echo:
        for line in lines:
            print(line)


def api_providers() -> dict[str, Any]:
    """Model-catalog providers. `text` and `vision` are the live endpoints.

    Text is a Meta model. Vision defaults to DeepSeek on Baseten and is not
    described as Meta. `baseten.base_url` is the previous response field.
    `modal` is omitted: Modal is not a vision host.
    """
    return {
        "text": public_settings(text_settings()),
        "vision": public_settings(vision_settings()),
        "baseten": {"base_url": BASETEN_BASE_URL},
    }


def list_agent_models() -> list[dict[str, Any]]:
    """Catalog for the Agent dashboard model dropdown."""
    cfg = text_settings()
    _reject_non_meta_target(cfg["model"], cfg["base_url"], kind="text")
    return [
        {
            "id": cfg["model"],
            "label": _model_label(cfg["model"]),
            "provider": cfg["provider"],
            "base_url": cfg["base_url"],
            "default": True,
        }
    ]


def resolve_model(model_id: str | None) -> dict[str, str]:
    cfg = text_settings()
    mid = (model_id or "").strip() or cfg["model"]
    _reject_non_meta_target(mid, cfg["base_url"], kind="text")
    for row in list_agent_models():
        if row["id"] == mid:
            return {"id": row["id"], "provider": row["provider"], "label": row["label"]}
    return {"id": mid, "provider": cfg["provider"], "label": _model_label(mid)}


def _client(cfg: dict[str, str], *, kind: str) -> OpenAI:
    if not cfg.get("api_key"):
        raise RuntimeError(
            f"{kind} provider misconfigured: set META_API_KEY, MODEL_API_KEY, "
            "or BASETEN_API_KEY in the repo root .env"
            + (
                " (or VISION_API_KEY / META_VISION_API_KEY for vision)"
                if kind == "vision"
                else ""
            )
        )
    if not cfg.get("base_url"):
        raise RuntimeError(f"{kind} provider misconfigured: base URL is empty")
    if not cfg.get("model"):
        raise RuntimeError(f"{kind} provider misconfigured: model name is empty")
    # Text stays on Meta. Vision is allowed to call DeepSeek or a later model.
    if kind != "vision":
        _reject_non_meta_target(cfg["model"], cfg["base_url"], kind=kind)
    return OpenAI(
        api_key=cfg["api_key"],
        base_url=cfg["base_url"],
        timeout=_timeout_seconds(kind),
        max_retries=0,
    )


def _bounded_float(raw: str, default: float, *, lo: float, hi: float) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = default
    return min(max(value, lo), hi)


def _timeout_seconds(kind: str) -> float:
    if kind == "vision":
        raw = _first_env(
            "VISION_TIMEOUT_SECONDS",
            "META_VISION_TIMEOUT_SECONDS",
            "META_TIMEOUT_SECONDS",
        )
        default = _DEFAULT_VISION_TIMEOUT
    else:
        raw = _first_env("META_TIMEOUT_SECONDS")
        default = _DEFAULT_TEXT_TIMEOUT
    return _bounded_float(raw or str(default), default, lo=0.2, hi=60.0)


def _max_retries() -> int:
    raw = _first_env("META_MAX_RETRIES") or str(_DEFAULT_MAX_RETRIES)
    try:
        value = int(raw)
    except ValueError:
        value = _DEFAULT_MAX_RETRIES
    return min(max(value, 0), 2)


def _public_model_error(exc: BaseException) -> str:
    """Short status for APIs and health. Details stay in the server log."""
    name = type(exc).__name__
    text = str(exc).lower()
    if "timeout" in name.lower() or "timed out" in text:
        return "model timed out"
    # Match the text-model refusal itself, before the generic misconfigured
    # check. A vision error that only quotes the DeepSeek model id is not this.
    if "not a meta model" in text or "refusing deepseek" in text:
        return "non-Meta model refused"
    if "misconfigured" in text or "api_key" in text or "key missing" in text or "not set" in text:
        return "model key missing or provider misconfigured"
    status = getattr(exc, "status_code", None)
    if status:
        return f"model request failed ({status})"
    return "model request failed"


def _retryable(exc: BaseException) -> bool:
    """One more try for a dropped connection or a gateway error, not for a hung read."""
    if "timeout" in type(exc).__name__.lower():
        return False
    status = getattr(exc, "status_code", None)
    if status in (408, 429, 500, 502, 503, 504):
        return True
    return type(exc).__name__ in {"APIConnectionError", "ConnectError", "ConnectionError"}


def note_model_success(kind: str) -> None:
    _model_status[kind] = {"ok": True, "error": None, "checked_at": time.time()}


def note_model_failure(kind: str, exc: BaseException) -> None:
    summary = _public_model_error(exc)
    log.error("Aurif %s model failed: %s (%s)", kind, summary, exc)
    _model_status[kind] = {"ok": False, "error": summary, "checked_at": time.time()}


def _chat(cfg: dict[str, str], *, kind: str, **kwargs: Any) -> Any:
    client = _client(cfg, kind=kind)
    attempts = 1 + _max_retries()
    last: BaseException | None = None
    for attempt in range(attempts):
        try:
            response = client.chat.completions.create(**kwargs)
        except Exception as exc:
            last = exc
            note_model_failure(kind, exc)
            if attempt + 1 >= attempts or not _retryable(exc):
                raise
            log.warning(
                "Aurif %s model call failed (%s); retry %s/%s",
                kind,
                _public_model_error(exc),
                attempt + 1,
                attempts - 1,
            )
            continue
        note_model_success(kind)
        return response
    assert last is not None
    raise last


# Bulk export and catalog extraction. Shopping words in the same sentence
# ("I am shopping") must not promote these to act when the model is down.
_BULK_EXTRACTION = re.compile(
    r"\b(?:export(?:ing|ed|s)?|csv|tsv|xlsx|spreadsheets?|excel)\b"
    r"|\b(?:every|all)\s+(?:the\s+)?(?:product\s+)?prices?\b"
    r"|\b(?:collect|gather|pull|extract|copy|download|harvest|scrape)(?:ing|ed|s)?\s+(?:every|all|the\s+(?:whole|entire))\b"
    r"|\b(?:download|export|copy|extract|scrape|harvest|dump)(?:ing|ed|s)?\s+(?:the\s+|a\s+)?(?:whole\s+|entire\s+|full\s+)?(?:catalog(?:ue)?|inventory|price\s+list)s?\b",
    re.I,
)


def rule_score_purpose(purpose: str) -> dict[str, Any]:
    """Conservative keyword score used only when the Meta model cannot answer.

    A clear shopping request may keep act. Bulk export, scraping, or bypass
    language stays view-only even when the same purpose also says it is shopping.
    Anything else, including an empty purpose, is view-only. This does not
    grant act just because the model is down.
    """
    text = (purpose or "").strip()
    if not text or text == "(empty)":
        scored = {
            "risk": "medium",
            "reason": "keyword rule: empty purpose, view only",
            "suggested_scopes": ["view"],
            "drop_act": True,
        }
    elif _HIGH_RISK.search(text) or _BULK_EXTRACTION.search(text):
        scored = {
            "risk": "high",
            "reason": "keyword rule: purpose looks like scraping, export, or bypass",
            "suggested_scopes": ["view"],
            "drop_act": True,
        }
    elif _SHOPPER.search(text):
        scored = {
            "risk": "low",
            "reason": "keyword rule: purpose looks like shopping help",
            "suggested_scopes": ["view", "act"],
            "drop_act": False,
        }
    else:
        scored = {
            "risk": "medium",
            "reason": "keyword rule: purpose is not clearly a shopper task, view only",
            "suggested_scopes": ["view"],
            "drop_act": True,
        }
    scored["source"] = "rules"
    scored["degraded"] = True
    scored["fallback"] = "keyword_rules"
    return scored


def _status_side(kind: str, cfg: dict[str, str]) -> dict[str, Any]:
    state = _model_status[kind]
    key_ok = bool(cfg.get("api_key"))
    configured = _vision_config_error(cfg) is None if kind == "vision" else key_ok
    if kind == "text" and key_ok:
        try:
            _reject_non_meta_target(cfg["model"], cfg["base_url"], kind="text")
        except RuntimeError:
            configured = False
    last_ok = state["ok"]
    degraded = (not configured) or last_ok is False
    card = _public_card(cfg)
    return {
        "provider": cfg.get("provider") or "",
        "model": cfg.get("model") or "",
        "label": card["label"],
        "family": card["family"],
        "powered_by": card["powered_by"],
        "base_url": cfg.get("base_url") or "",
        "key_configured": key_ok,
        "timeout_seconds": _timeout_seconds(kind),
        "max_retries": _max_retries(),
        "last_ok": last_ok,
        "last_error": state["error"],
        "checked_at": state["checked_at"],
        "degraded": degraded,
    }


def vision_configured() -> bool:
    return _vision_config_error(vision_settings()) is None


def reset_model_status() -> None:
    for kind in _model_status:
        _model_status[kind] = {"ok": None, "error": None, "checked_at": None}


def health_snapshot() -> dict[str, Any]:
    """Operator view of model config and the last call. No API key material."""
    text = _status_side("text", text_settings())
    vision = _status_side("vision", vision_settings())
    degraded = bool(text["degraded"] or vision["degraded"])
    return {
        "ok": not degraded,
        "degraded": degraded,
        "text": text,
        "vision": vision,
        "fallbacks": {
            "handshake": "keyword_rules",
            "captcha": "typed_code_or_ink",
        },
    }


def _message_text(msg: Any) -> str:
    content = getattr(msg, "content", None) or ""
    if content:
        return str(content).strip()
    reasoning = getattr(msg, "reasoning_content", None) or ""
    return str(reasoning).strip()


def complete(
    messages: list[dict[str, Any]],
    *,
    max_tokens: int = 1200,
    temperature: float = 0.2,
    model: str | None = None,
    provider: str | None = None,
) -> str:
    cfg = text_settings()
    resolved = resolve_model(model)
    # Provider is a label (meta, baseten, llama-api, …). The host is the base URL.
    # A mismatched label must not switch the request onto another vendor.
    _ = provider or resolved["provider"]
    kwargs: dict[str, Any] = {
        "model": resolved["id"],
        "messages": messages,
        "stream": False,
        "max_tokens": _output_tokens(max_tokens, cfg["base_url"]),
    }
    # Send temperature only. Meta Model API rejects temperature together with top_p.
    if temperature is not None:
        kwargs["temperature"] = temperature
    extra = _meta_extra(cfg["base_url"])
    if extra:
        kwargs["extra_body"] = extra
    response = _chat(cfg, kind="text", **kwargs)
    return _message_text(response.choices[0].message)


def extract_json(text: str) -> Any:
    """Parse JSON from model output, tolerating markdown fences and trailing junk."""
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    decoder = json.JSONDecoder()
    candidates: list[Any] = []
    for i, ch in enumerate(raw):
        if ch not in "{[":
            continue
        try:
            obj, _ = decoder.raw_decode(raw[i:])
            candidates.append(obj)
        except json.JSONDecodeError:
            continue
    for obj in candidates:
        if isinstance(obj, dict) and (
            "summary" in obj or "risk" in obj or "patches" in obj or "done" in obj
        ):
            return obj
    for obj in candidates:
        if isinstance(obj, dict):
            return obj
    if candidates:
        return candidates[0]
    return json.loads(raw)


def score_purpose(purpose: str) -> dict[str, Any]:
    """Classify agent handshake purpose for risk."""
    purpose = (purpose or "").strip() or "(empty)"
    started = time.perf_counter()
    card = model_card()
    prompt = f"""You are Aurif's handshake risk classifier for a commerce website.
Score this AI agent purpose. Reply with ONLY valid JSON:
{{"risk":"low"|"medium"|"high","reason":"short reason","suggested_scopes":["view"] or ["view","act"],"drop_act":true|false}}

Rules:
- high + drop_act true: scraping prices, bulk harvesting, resale, competitors, bypassing policy
- medium: vague purpose, research without clear user help
- low + act allowed: help a user browse/buy under site rules

Purpose: {purpose}
"""

    def rules(exc: BaseException | None) -> dict[str, Any]:
        scored = rule_score_purpose(purpose)
        scored["warning"] = _owner_warning("handshake", exc)
        return _stamp_call(scored, started=started, card=card)

    try:
        data = extract_json(
            complete([{"role": "user", "content": prompt}], max_tokens=800, temperature=0.1)
        )
    except Exception as exc:
        log.warning(
            "handshake risk model unavailable (%s); using keyword rules",
            _public_model_error(exc),
        )
        return rules(exc)
    if not isinstance(data, dict):
        log.warning("handshake risk model returned a non-object payload; using keyword rules")
        note_model_failure("text", RuntimeError("risk model returned a non-object payload"))
        return rules(RuntimeError("risk model returned a non-object payload"))
    risk = str(data.get("risk") or "medium").lower()
    if risk not in ("low", "medium", "high"):
        risk = "medium"
    scopes = data.get("suggested_scopes") or ["view"]
    if not isinstance(scopes, list):
        scopes = ["view"]
    scopes = [s for s in scopes if s in ("view", "act")]
    if not scopes:
        scopes = ["view"]
    drop_act = bool(data.get("drop_act")) or risk == "high"
    if drop_act:
        scopes = [s for s in scopes if s != "act"] or ["view"]
    return _stamp_call(
        {
            "risk": risk,
            "reason": str(data.get("reason") or "")[:300],
            "suggested_scopes": scopes,
            "drop_act": drop_act,
            "source": "model",
            "degraded": False,
            "fallback": None,
        },
        started=started,
        card=card,
    )


_CLOSE = re.compile(
    r"\b(disable|disabled|turn off|turns off|close|closed|block|blocked|deny|denied|shut|stop)\b",
    re.I,
)
_HIDE = re.compile(r"\b(hide|hidden|omit|omitted|redact|redacted|strip|mask|conceal|private)\b", re.I)
_PRICE = re.compile(r"\b(prices?|pricing|compare[- ]?at|discounts?)\b", re.I)
_EMAIL = re.compile(r"\b(e-?mails?)\b", re.I)
_SENSITIVE_KEY = re.compile(r"price|compare_at|compareat|discount", re.I)
_POLICY_STOP = {
    "page",
    "pages",
    "action",
    "actions",
    "agent",
    "agents",
    "from",
    "with",
    "this",
    "that",
    "your",
    "site",
    "the",
    "and",
    "for",
    "all",
    "any",
    "endpoint",
    "endpoints",
    "field",
    "fields",
    "json",
    "access",
    "hide",
    "disable",
    "close",
    "block",
    "turn",
    "stop",
    "deny",
    "shut",
    "off",
}


def _endpoint_terms(ep: dict[str, Any]) -> set[str]:
    blob = " ".join(
        str(ep.get(key) or "") for key in ("id", "label", "path", "action_id", "ref")
    ).lower()
    return {
        part
        for part in re.split(r"[^a-z0-9]+", blob)
        if len(part) >= 4 and part not in _POLICY_STOP
    }


def rule_propose_policy(
    instruction: str,
    endpoints: list[dict[str, Any]],
    *,
    unavailable: str | None = None,
) -> dict[str, Any]:
    """Keyword policy draft used only when the Meta model cannot answer.

    The result is a proposal. Callers must not write it until the owner applies it.
    """
    text = (instruction or "").strip()
    hide_price = bool(_HIDE.search(text) and _PRICE.search(text))
    hide_email = bool((_HIDE.search(text) or _CLOSE.search(text)) and _EMAIL.search(text))
    wants_close = bool(_CLOSE.search(text))
    by_id: dict[str, dict[str, Any]] = {}

    def slot(endpoint_id: str) -> dict[str, Any]:
        row = by_id.get(endpoint_id)
        if row is None:
            row = {"endpoint_id": endpoint_id}
            by_id[endpoint_id] = row
        return row

    notes: list[str] = []
    if hide_price:
        touched = 0
        for ep in endpoints:
            fields = []
            for field in ep.get("response_fields") or []:
                key = str(field.get("key") or "")
                if key and _SENSITIVE_KEY.search(key):
                    fields.append({"key": key, "agent_visible": False})
            if fields:
                slot(str(ep.get("id")))["response_fields"] = fields
                touched += 1
        if touched:
            notes.append(f"hide price fields on {touched} endpoint(s)")

    if hide_email:
        touched = 0
        for ep in endpoints:
            fields = []
            for field in ep.get("request_fields") or []:
                key = str(field.get("key") or "")
                if "email" in key.lower():
                    fields.append({"key": key, "agent_allowed": False})
            if fields:
                slot(str(ep.get("id")))["request_fields"] = fields
                touched += 1
        if touched:
            notes.append("reject email on agent requests")

    if wants_close:
        instruction_terms = {
            part
            for part in re.split(r"[^a-z0-9]+", text.lower())
            if len(part) >= 4 and part not in _POLICY_STOP
        }
        closed: list[str] = []
        for ep in endpoints:
            if not (_endpoint_terms(ep) & instruction_terms):
                continue
            slot(str(ep.get("id")))["agent_access"] = False
            closed.append(str(ep.get("label") or ep.get("id")))
        if closed:
            notes.append("close " + ", ".join(closed[:6]))

    blocked: list[str] = []
    for match in re.finditer(r"\bblock(?:ed)?\s+agent\s+([A-Za-z0-9_.:-]{2,64})", text, re.I):
        name = match.group(1)
        if name not in blocked:
            blocked.append(name)
    if blocked:
        notes.append("block " + ", ".join(blocked))

    if notes:
        summary = "Keyword rule: " + "; ".join(notes) + "."
    else:
        summary = "Keyword rule: no page, field, or agent matched this instruction. Nothing is proposed."

    detail = unavailable or "model request failed"
    return {
        "summary": summary,
        "patches": list(by_id.values()),
        "blocked_agents_add": blocked,
        "source": "rules",
        "degraded": True,
        "fallback": "keyword_rules",
        "warning": (
            f"Meta model unavailable ({detail}). "
            "This proposal is a keyword-rules fallback and is not applied until you confirm."
        ),
    }


def propose_policy(instruction: str, endpoints: list[dict[str, Any]]) -> dict[str, Any]:
    """NL → endpoint/field patches matching Aurif store shapes."""
    slim = []
    for ep in endpoints:
        slim.append(
            {
                "id": ep.get("id"),
                "label": ep.get("label"),
                "kind": ep.get("kind"),
                "agent_access": ep.get("agent_access"),
                "response_fields": [
                    {"key": f.get("key"), "agent_visible": f.get("agent_visible", True)}
                    for f in (ep.get("response_fields") or [])
                ],
                "request_fields": [
                    {"key": f.get("key"), "agent_allowed": f.get("agent_allowed", True)}
                    for f in (ep.get("request_fields") or [])
                ],
            }
        )
    prompt = f"""You are Aurif's owner policy co-pilot. Convert the owner's instruction into JSON patches.
Reply with ONLY valid JSON:
{{
  "summary": "one sentence",
  "patches": [
    {{"endpoint_id":"<id>","agent_access":true|false}},
    {{"endpoint_id":"<id>","response_fields":[{{"key":"meta.price","agent_visible":false}}]}},
    {{"endpoint_id":"<id>","request_fields":[{{"key":"email","agent_allowed":false}}]}}
  ],
  "blocked_agents_add": []
}}

Only reference endpoint ids and field keys from this schema:
{json.dumps(slim, indent=2)}

Owner instruction: {instruction}
"""
    started = time.perf_counter()
    card = model_card()

    def rules(exc: BaseException) -> dict[str, Any]:
        log.warning(
            "policy model unavailable (%s); using keyword rules",
            _public_model_error(exc),
        )
        return _stamp_call(
            rule_propose_policy(instruction, endpoints, unavailable=_public_model_error(exc)),
            started=started,
            card=card,
        )

    try:
        data = extract_json(
            complete([{"role": "user", "content": prompt}], max_tokens=2500, temperature=0.1)
        )
    except Exception as exc:
        return rules(exc)
    if not isinstance(data, dict):
        note_model_failure("text", RuntimeError("policy model returned a non-object payload"))
        return rules(RuntimeError("policy model returned a non-object payload"))
    patches = data.get("patches") or []
    if not isinstance(patches, list):
        patches = []
    known = {ep.get("id") for ep in endpoints}
    patches = [p for p in patches if isinstance(p, dict) and p.get("endpoint_id") in known]
    blocked = data.get("blocked_agents_add") or []
    if not isinstance(blocked, list):
        blocked = []
    return _stamp_call(
        {
            "summary": str(data.get("summary") or "Policy proposal"),
            "patches": patches,
            "blocked_agents_add": blocked,
            "source": "model",
            "degraded": False,
            "fallback": None,
        },
        started=started,
        card=card,
    )


def _activity_brief(
    kinds: Counter[str],
    agents: Counter[str],
    high_risk: list[dict[str, str]],
    denied: list[str],
    redacted: Counter[str],
    actions: Counter[str],
    event_count: int,
) -> dict[str, Any]:
    """Count-accurate owner summary — primary path for precision."""
    hs = kinds.get("handshake", 0)
    pages = kinds.get("page", 0)
    acts = kinds.get("action", 0)
    blocks = (
        kinds.get("handshake_denied", 0)
        + kinds.get("action_blocked", 0)
        + kinds.get("page_blocked", 0)
    )
    hides = kinds.get("field_redacted", 0)

    line1 = (
        f"{event_count} events from {len(agents)} agents: "
        f"{hs} handshakes, {pages} page reads, {acts} actions"
    )
    if blocks:
        line1 += f", {blocks} blocks"
    if hides:
        line1 += f", {hides} field hides"
    line1 += "."

    risky_ids: list[str] = []
    seen: set[str] = set()
    for hr in high_risk:
        aid = hr["agent_id"]
        if aid in seen:
            continue
        seen.add(aid)
        risky_ids.append(aid)
        if len(risky_ids) >= 2:
            break

    if risky_ids:
        reason = next(
            (hr.get("reason") for hr in high_risk if hr["agent_id"] == risky_ids[0]),
            "high-risk purpose",
        )
        short_reason = (reason or "high-risk purpose").split(".")[0][:80]
        line2 = (
            f"{risky_ids[0]} flagged high risk ({short_reason}) "
            f"and was limited to view-only."
        )
    elif denied:
        line2 = f"{len(set(denied))} agent(s) hit deny/block responses."
    else:
        line2 = "No high-risk purposes in this window."

    if redacted:
        top = ", ".join(f"{k}×{v}" for k, v in redacted.most_common(2))
        line3 = f"Hidden from agents: {top}."
    elif actions:
        line3 = f"Top action: {actions.most_common(1)[0][0]}."
    else:
        line3 = ""

    summary = " ".join(p for p in (line1, line2, line3) if p)

    risk_bits: list[str] = []
    for aid in risky_ids:
        hr = next(h for h in high_risk if h["agent_id"] == aid)
        risk_bits.append(f"{aid}: {(hr.get('reason') or hr.get('purpose') or 'high risk')[:90]}")
    for aid in sorted(set(denied))[:2]:
        if aid not in seen:
            risk_bits.append(f"{aid}: blocked or denied by policy")

    abuse_words = ("scrape", "resale", "harvest", "competitor")
    block_suggest = []
    for aid in risky_ids:
        blob = " ".join(
            (hr.get("purpose") or "") + " " + (hr.get("reason") or "")
            for hr in high_risk
            if hr["agent_id"] == aid
        ).lower()
        if any(w in blob for w in abuse_words):
            block_suggest.append(aid)

    return {
        "summary": summary,
        "risks": risk_bits[:4],
        "suggested_blocked_agents": block_suggest[:5],
    }


def summarize_activity(events: list[dict[str, Any]]) -> dict[str, Any]:
    kinds: Counter[str] = Counter()
    agents: Counter[str] = Counter()
    high_risk: list[dict[str, str]] = []
    denied: list[str] = []
    redacted: Counter[str] = Counter()
    actions: Counter[str] = Counter()

    for e in events[:100]:
        kind = str(e.get("kind") or "unknown")
        agent = str(e.get("agent_id") or "unknown")
        kinds[kind] += 1
        agents[agent] += 1
        detail = e.get("detail") if isinstance(e.get("detail"), dict) else {}
        risk = detail.get("purpose_risk") if isinstance(detail.get("purpose_risk"), dict) else {}
        if risk.get("risk") == "high" or risk.get("drop_act"):
            high_risk.append(
                {
                    "agent_id": agent,
                    "purpose": str(detail.get("purpose") or "")[:120],
                    "reason": str(risk.get("reason") or "")[:160],
                }
            )
        if kind in ("handshake_denied", "action_blocked", "page_blocked"):
            denied.append(agent)
        for f in detail.get("redacted_fields") or []:
            redacted[str(f)] += 1
        if e.get("action_id"):
            actions[str(e.get("action_id"))] += 1

    brief = _activity_brief(
        kinds,
        agents,
        high_risk,
        denied,
        redacted,
        actions,
        event_count=min(len(events), 100),
    )

    # Optional Muse polish — keep only if terse and grounded. Counts stay local.
    polish_prompt = f"""Tighten this Aurif audit into JSON.
Rules: max 2 sentences in summary; max 3 risk bullets; each risk ≤12 words; keep every number exact; invent nothing.
Return ONLY JSON: {{"summary":"...","risks":["..."],"suggested_blocked_agents":["..."]}}

Draft:
{json.dumps(brief)}
"""
    started = time.perf_counter()
    card = model_card()
    model_error: str | None = None
    polished: Any = None
    try:
        polished = extract_json(
            complete(
                [
                    {
                        "role": "system",
                        "content": "Return one terse JSON object. Never invent facts.",
                    },
                    {"role": "user", "content": polish_prompt},
                ],
                max_tokens=600,
                temperature=0.1,
            )
        )
    except Exception as exc:
        model_error = _public_model_error(exc)
        log.warning("activity summary model unavailable (%s); using counted brief", model_error)
        polished = None

    data = brief
    used_model = False
    if isinstance(polished, dict):
        summary = str(polished.get("summary") or "").strip()
        words = len(summary.split())
        event_n = str(min(len(events), 100))
        grounded = event_n in summary and "agent" in summary.lower()
        if 15 <= words <= 50 and grounded:
            known = {h["agent_id"] for h in high_risk} | set(denied)
            risks = polished.get("risks") if isinstance(polished.get("risks"), list) else []
            risks = [str(r)[:120] for r in risks[:3]]
            blocked = polished.get("suggested_blocked_agents")
            if not isinstance(blocked, list):
                blocked = brief["suggested_blocked_agents"]
            blocked = [str(a) for a in blocked[:5] if str(a) in known]
            data = {
                "summary": summary,
                "risks": risks or brief["risks"],
                "suggested_blocked_agents": blocked or brief["suggested_blocked_agents"],
            }
            used_model = True

    if model_error:
        source = "rules"
        degraded = True
        fallback = "activity_counts"
        warning = _owner_warning("activity", RuntimeError(model_error))
    elif used_model:
        source = "model"
        degraded = False
        fallback = None
        warning = None
    else:
        source = "rules"
        degraded = False
        fallback = "activity_counts"
        warning = "The model reply did not keep the counted facts. Showing the local summary."

    stamped = _stamp_call(
        {
            "summary": str(data.get("summary") or "").strip(),
            "risks": data.get("risks") if isinstance(data.get("risks"), list) else [],
            "suggested_blocked_agents": data.get("suggested_blocked_agents")
            if isinstance(data.get("suggested_blocked_agents"), list)
            else [],
            "source": source,
            "degraded": degraded,
            "fallback": fallback,
        },
        started=started,
        card=card,
    )
    if warning:
        stamped["warning"] = warning
    return stamped


def _vision_config_error(cfg: dict[str, str]) -> str | None:
    if not cfg.get("api_key"):
        return (
            "vision provider misconfigured: set VISION_API_KEY or BASETEN_API_KEY "
            "in the repo root .env (META_VISION_API_KEY still applies when VISION_API_KEY is unset)"
        )
    if not cfg.get("base_url"):
        return "vision provider misconfigured: VISION_BASE_URL / META_VISION_BASE_URL is empty"
    if not cfg.get("model"):
        return "vision provider misconfigured: VISION_MODEL / META_VISION_MODEL is empty"
    return None


def _as_bool(value: Any) -> bool:
    """True only for real truthy flags. The string \"false\" must not pass."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value == 1
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1"}
    return False


def _norm_glyph(value: str) -> str:
    return "".join(ch for ch in (value or "").upper() if ch.isalnum())


# First token of the vision reason. A lenient model that says match=true and
# also admits the pad is blank or scribbled is still a rejection.
_REJECT_REASONS = {
    "blank",
    "empty",
    "scribble",
    "scribbled",
    "doodle",
    "mismatch",
    "wrong",
    "unrelated",
    "gibberish",
    "unclear",
    "unreadable",
    "typed",
    "typed_or_machine",
    "machine",
    "screenshot",
}


def _reason_code(reason: str) -> str:
    token = (reason or "").strip().lower().split(" ", 1)[0] if reason else ""
    return token.strip(".,:;\"'")


def _judge_drawing(data: dict[str, Any], target: str) -> dict[str, Any]:
    """Strict parse of the vision JSON.

    A pass needs match, a hand-drawn flag, and read_as equal to the prompt.
    Blank, scribbled, or non-matching drawings fail. A correct read_as does
    not override match=false.
    """
    match = _as_bool(data.get("match"))
    human_like = _as_bool(data.get("human_like")) if "human_like" in data else False
    read_as = _norm_glyph(str(data.get("read_as") or ""))
    expected = _norm_glyph(target)
    reason = str(data.get("reason") or "")[:200]
    if _reason_code(reason) in _REJECT_REASONS:
        match = False
    if "confidence" in data and data.get("confidence") is not None:
        try:
            confidence = float(data.get("confidence"))
        except (TypeError, ValueError):
            confidence = 0.0
        if confidence < 0.8:
            match = False
            if not reason:
                reason = "low confidence"
    if not read_as or read_as != expected:
        match = False
        if not reason:
            reason = "drawing does not match the prompt" if read_as else "could not read the drawing"
    if match and not human_like and not reason:
        reason = "looks machine-made, not hand-drawn"
    ok = bool(match and human_like and read_as == expected and expected)
    return {
        "ok": ok,
        "match": match,
        "human_like": human_like,
        "read_as": read_as,
        "reason": reason,
    }


def verify_drawing(image_data_url: str, target: str) -> dict[str, Any]:
    """Vision check: does the sketch show the requested characters?

    Calls the configured vision model (DeepSeek on Baseten by default).
    A missing key or an upstream error is returned as unavailable so the
    human gate can open the storefront without granting agent act.
    A readable judgement that does not match is a hard rejection.
    """
    cfg = vision_settings()
    identity = _vision_identity(cfg)
    target = (target or "").strip().upper()
    raw = (image_data_url or "").strip()
    if not raw.startswith("data:image/"):
        return {"ok": False, "reason": "expected a drawing image", **identity}
    if len(raw) > 1_800_000:
        return {"ok": False, "reason": "drawing too large", **identity}

    problem = _vision_config_error(cfg)
    if problem:
        note_model_failure("vision", RuntimeError(problem))
        return {"ok": False, "unavailable": True, "reason": problem, **identity}

    prompt = f"""CAPTCHA check. The required drawing is exactly "{target}".

You are a strict vision judge. Pass only a hand-drawn "{target}".
Reject anything else.

Set match=false when any of these are true:
- the pad is blank, nearly blank, a single stroke, a scribble, a doodle, or random marks
- the drawing is a different character, word, number, or object than "{target}"
- you are unsure what the strokes depict
- the marks are typed text, a font, a screenshot, or machine-rendered

Set match=true only when the strokes are clearly "{target}" and nothing else.
Set human_like=true only for uneven mouse or finger strokes.
Set human_like=false for typed, perfect, blank, or machine-made marks.
Set read_as to only the characters you can actually see, in order, or "" if you cannot read them.
Do not copy "{target}" into read_as unless those exact characters are visible.
Set confidence from 0 to 1. Use a value below 0.8 when the drawing is unclear, partial, or scribbled.

Reply with ONE JSON object and no markdown:
{{"match":false,"human_like":false,"read_as":"","confidence":0,"reason":"blank"}}
or, only for a clear hand drawing of "{target}":
{{"match":true,"human_like":true,"read_as":"{target}","confidence":0.95,"reason":"ok"}}
"""
    # Images are only honored on user messages (Meta Model API returns 400 otherwise).
    messages = [
        {
            "role": "system",
            "content": (
                "You are a strict CAPTCHA judge. Reject blank, scribbled, and "
                "non-matching drawings. End with one JSON object."
            ),
        },
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": raw}},
            ],
        },
    ]

    try:
        kwargs: dict[str, Any] = {
            "model": cfg["model"],
            "messages": messages,
            "stream": False,
            "max_tokens": _output_tokens(2048, cfg["base_url"]),
            "temperature": 0.1,
        }
        extra = _meta_extra(cfg["base_url"])
        if extra:
            kwargs["extra_body"] = extra
        response = _chat(cfg, kind="vision", **kwargs)
        text = _message_text(response.choices[0].message)
    except Exception as err:
        return {
            "ok": False,
            "unavailable": True,
            "reason": f"vision provider error ({identity['provider']} {identity['model']}): {err}",
            **identity,
        }

    try:
        data = extract_json(text)
    except Exception:
        brace = text.rfind("{")
        data = None
        if brace >= 0:
            try:
                data = extract_json(text[brace:])
            except Exception:
                data = None
        if not isinstance(data, dict):
            note_model_failure("vision", RuntimeError("vision model returned unreadable result"))
            return {
                "ok": False,
                "unavailable": True,
                "reason": "vision model returned unreadable result",
                "raw": text[:200],
                **identity,
            }
    if not isinstance(data, dict):
        note_model_failure("vision", RuntimeError("invalid vision response"))
        return {
            "ok": False,
            "unavailable": True,
            "reason": "invalid vision response",
            **identity,
        }

    judged = _judge_drawing(data, target)
    return {"unavailable": False, **judged, **identity}
