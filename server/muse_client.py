"""Meta model client for Aurif product AI features.

Preferred host is the Meta Model API (Muse Spark 1.3). If that key is unset
and BASETEN_API_KEY is present, text and vision stay on Baseten Muse Spark
Open (meta-models/muse-spark-open-1026), which already accepted CAPTCHA images.
DeepSeek and Modal are not used.
"""

from __future__ import annotations

import json
import logging
import os
import re
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

log = logging.getLogger("aurif.models")

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
    """Vision endpoint. Unset vision vars inherit the text Meta endpoint."""
    text = text_settings()
    return {
        "provider": _first_env("META_VISION_PROVIDER") or text["provider"],
        "base_url": (_first_env("META_VISION_BASE_URL") or text["base_url"]).rstrip("/"),
        "model": _first_env("META_VISION_MODEL") or text["model"],
        "api_key": _first_env("META_VISION_API_KEY") or text["api_key"],
    }


def public_settings(cfg: dict[str, str]) -> dict[str, str]:
    """Settings safe to return from an API (no key)."""
    return {
        "provider": cfg.get("provider") or "",
        "base_url": cfg.get("base_url") or "",
        "model": cfg.get("model") or "",
    }


def text_model_id() -> str:
    return text_settings()["model"]


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


def _model_label(model_id: str) -> str:
    tail = (model_id or "").split("/")[-1]
    if "muse-spark-open" in model_id:
        return "Muse Spark Open"
    if tail.startswith("muse-spark"):
        rest = tail.removeprefix("muse-spark").lstrip("-")
        return f"Muse Spark {rest}".strip() if rest else "Muse Spark"
    return tail or model_id


def log_active_models(*, echo: bool = False) -> None:
    """Log the text and vision provider/model. Never includes the API key."""
    lines: list[str] = []
    for kind, loader in (("text", text_settings), ("vision", vision_settings)):
        cfg = loader()
        try:
            _reject_non_meta_target(cfg["model"], cfg["base_url"], kind=kind)
            line = (
                f"Aurif {kind} model: provider={cfg['provider']} "
                f"model={cfg['model']} base_url={cfg['base_url']} "
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

    `baseten.base_url` is the previous response field. `modal` is omitted:
    it was the DeepSeek host, and the dashboard does not read `providers`.
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
                " (or META_VISION_API_KEY for vision)"
                if kind == "vision"
                else ""
            )
        )
    if not cfg.get("base_url"):
        raise RuntimeError(f"{kind} provider misconfigured: base URL is empty")
    if not cfg.get("model"):
        raise RuntimeError(f"{kind} provider misconfigured: model name is empty")
    _reject_non_meta_target(cfg["model"], cfg["base_url"], kind=kind)
    return OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"])


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
    client = _client(cfg, kind="text")
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
    response = client.chat.completions.create(**kwargs)
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
    prompt = f"""You are Aurif's handshake risk classifier for a commerce website.
Score this AI agent purpose. Reply with ONLY valid JSON:
{{"risk":"low"|"medium"|"high","reason":"short reason","suggested_scopes":["view"] or ["view","act"],"drop_act":true|false}}

Rules:
- high + drop_act true: scraping prices, bulk harvesting, resale, competitors, bypassing policy
- medium: vague purpose, research without clear user help
- low + act allowed: help a user browse/buy under site rules

Purpose: {purpose}
"""
    try:
        data = extract_json(
            complete([{"role": "user", "content": prompt}], max_tokens=800, temperature=0.1)
        )
    except Exception as e:
        return {
            "risk": "medium",
            "reason": f"risk model unavailable: {e}",
            "suggested_scopes": ["view"],
            "drop_act": True,
            "error": str(e),
        }
    if not isinstance(data, dict):
        return {
            "risk": "medium",
            "reason": "risk model returned a non-object payload",
            "suggested_scopes": ["view"],
            "drop_act": True,
        }
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
    return {
        "risk": risk,
        "reason": str(data.get("reason") or "")[:300],
        "suggested_scopes": scopes,
        "drop_act": drop_act,
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
    data = extract_json(
        complete([{"role": "user", "content": prompt}], max_tokens=2500, temperature=0.1)
    )
    if not isinstance(data, dict):
        raise ValueError("policy model did not return a JSON object")
    patches = data.get("patches") or []
    if not isinstance(patches, list):
        patches = []
    known = {ep.get("id") for ep in endpoints}
    patches = [p for p in patches if isinstance(p, dict) and p.get("endpoint_id") in known]
    return {
        "summary": str(data.get("summary") or "Policy proposal"),
        "patches": patches,
        "blocked_agents_add": data.get("blocked_agents_add") or [],
    }


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

    # Optional Muse polish — keep only if terse and grounded
    polish_prompt = f"""Tighten this Aurif audit into JSON.
Rules: max 2 sentences in summary; max 3 risk bullets; each risk ≤12 words; keep every number exact; invent nothing.
Return ONLY JSON: {{"summary":"...","risks":["..."],"suggested_blocked_agents":["..."]}}

Draft:
{json.dumps(brief)}
"""
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
    except Exception:
        polished = None

    data = brief
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

    return {
        "summary": str(data.get("summary") or "").strip(),
        "risks": data.get("risks") if isinstance(data.get("risks"), list) else [],
        "suggested_blocked_agents": data.get("suggested_blocked_agents")
        if isinstance(data.get("suggested_blocked_agents"), list)
        else [],
    }


def _vision_config_error(cfg: dict[str, str]) -> str | None:
    try:
        if not cfg.get("api_key"):
            return (
                "vision provider misconfigured: set META_VISION_API_KEY, "
                "META_API_KEY, MODEL_API_KEY, or BASETEN_API_KEY in the repo root .env"
            )
        if not cfg.get("base_url"):
            return "vision provider misconfigured: META_VISION_BASE_URL / META_BASE_URL is empty"
        if not cfg.get("model"):
            return "vision provider misconfigured: META_VISION_MODEL / META_MODEL is empty"
        _reject_non_meta_target(cfg["model"], cfg["base_url"], kind="vision")
    except RuntimeError as e:
        return str(e)
    return None


def verify_drawing(image_data_url: str, target: str) -> dict[str, Any]:
    """Vision check: does the sketch show the target?

    Uses only the configured Meta vision model. A missing key, a DeepSeek model
    id, or an upstream error is returned to the caller. There is no fallback.
    """
    cfg = vision_settings()
    model = cfg["model"]
    provider = cfg["provider"]
    target = (target or "").strip().upper()
    raw = (image_data_url or "").strip()
    if not raw.startswith("data:image/"):
        return {"ok": False, "reason": "expected a drawing image", "model": model, "provider": provider}
    if len(raw) > 1_800_000:
        return {"ok": False, "reason": "drawing too large", "model": model, "provider": provider}

    problem = _vision_config_error(cfg)
    if problem:
        return {"ok": False, "reason": problem, "model": model, "provider": provider}

    prompt = f"""CAPTCHA check. Target to draw: "{target}"

Look at the image. Decide if a human roughly hand-drew "{target}".
Imperfect strokes OK.

Rules:
- match=true only if the drawing shows "{target}"
- human_like=true only for messy hand strokes (mouse/finger sketch)
- human_like=false for typed fonts, perfect glyphs, screenshots, blank, or bot-rendered text
- Reject blank or wrong characters with match=false

End your reply with ONE JSON object (no markdown):
{{"match":true,"human_like":true,"read_as":"{target}","reason":"ok"}}
or
{{"match":false,"human_like":false,"read_as":"","reason":"blank"}}
or
{{"match":true,"human_like":false,"read_as":"{target}","reason":"typed_or_machine"}}
"""
    # Images are only honored on user messages (Meta Model API returns 400 otherwise).
    messages = [
        {
            "role": "system",
            "content": "You verify drawings. Always end with a single JSON object.",
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
        client = _client(cfg, kind="vision")
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "max_tokens": _output_tokens(2048, cfg["base_url"]),
            "temperature": 0.1,
        }
        extra = _meta_extra(cfg["base_url"])
        if extra:
            kwargs["extra_body"] = extra
        response = client.chat.completions.create(**kwargs)
        text = _message_text(response.choices[0].message)
    except Exception as err:
        return {
            "ok": False,
            "reason": f"vision provider error ({provider} {model}): {err}",
            "model": model,
            "provider": provider,
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
            return {
                "ok": False,
                "reason": "vision model returned unreadable result",
                "raw": text[:200],
                "model": model,
                "provider": provider,
            }
    if not isinstance(data, dict):
        return {
            "ok": False,
            "reason": "invalid vision response",
            "model": model,
            "provider": provider,
        }

    match = bool(data.get("match"))
    # Default False: missing human_like must not accidentally pass bots.
    human_like = bool(data.get("human_like")) if "human_like" in data else False
    read_as = str(data.get("read_as") or "").strip().upper().replace(" ", "")
    reason = str(data.get("reason") or "")[:200]
    # Correct glyph alone is not enough — typed/bot renders often match the target.
    if not match and read_as == target and human_like:
        match = True
    ok = bool(match and human_like)
    if match and not human_like and not reason:
        reason = "looks machine-made, not hand-drawn"
    return {
        "ok": ok,
        "match": match,
        "human_like": human_like,
        "read_as": read_as,
        "reason": reason,
        "model": model,
        "provider": provider,
    }
