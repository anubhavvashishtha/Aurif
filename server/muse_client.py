"""Baseten Muse Spark Open client for Aurif product AI features."""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
# override=True so restarted Flask picks up tokens added to .env after process start
load_dotenv(ROOT / ".env", override=True)

BASETEN_BASE_URL = "https://inference.baseten.co/v1"
# Hackathon model id — plain muse-spark-open returns 403 with participant keys
DEFAULT_MODEL = os.environ.get("BASETEN_MODEL", "meta-models/muse-spark-open-1026")

# Modal DeepSeek vision endpoint (draw CAPTCHA)
MODAL_BASE_URL = os.environ.get(
    "MODAL_BASE_URL",
    "https://anubhavvashishtha-iitd--ep-deepseek-v4-1-flash-server.us-west.modal.direct/v1",
).rstrip("/")
VISION_MODEL = os.environ.get("MODAL_VISION_MODEL", "deepseek-ai/DeepSeek-V4.1-Flash")


def _api_key() -> str:
    key = (os.environ.get("BASETEN_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("BASETEN_API_KEY missing — set it in the repo root .env")
    return key


def _modal_api_key() -> str:
    tid = (os.environ.get("MODAL_TOKEN_ID") or "").strip()
    secret = (os.environ.get("MODAL_TOKEN_SECRET") or "").strip()
    if not tid or not secret:
        raise RuntimeError(
            "MODAL_TOKEN_ID and MODAL_TOKEN_SECRET required in repo root .env for vision CAPTCHA"
        )
    return f"{tid}.{secret}"


def get_client() -> OpenAI:
    return OpenAI(api_key=_api_key(), base_url=BASETEN_BASE_URL)


def get_modal_client() -> OpenAI:
    return OpenAI(api_key=_modal_api_key(), base_url=MODAL_BASE_URL)


def _message_text(msg: Any) -> str:
    content = getattr(msg, "content", None) or ""
    if content:
        return str(content).strip()
    reasoning = getattr(msg, "reasoning_content", None) or ""
    return str(reasoning).strip()


def complete(
    messages: list[dict[str, str]],
    *,
    max_tokens: int = 1200,
    temperature: float = 0.2,
    model: str | None = None,
) -> str:
    client = get_client()
    response = client.chat.completions.create(
        model=model or DEFAULT_MODEL,
        messages=messages,
        stream=False,
        max_tokens=max_tokens,
        temperature=temperature,
    )
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


def verify_drawing(image_data_url: str, target: str) -> dict[str, Any]:
    """Vision check via Modal DeepSeek: does the sketch show the target?"""
    # Refresh secrets from .env on each verify (dev-friendly)
    load_dotenv(ROOT / ".env", override=True)
    target = (target or "").strip().upper()
    raw = (image_data_url or "").strip()
    if not raw.startswith("data:image/"):
        return {"ok": False, "reason": "expected a drawing image", "model": VISION_MODEL}
    if len(raw) > 1_800_000:
        return {"ok": False, "reason": "drawing too large", "model": VISION_MODEL}

    prompt = f"""CAPTCHA check. Target to draw: "{target}"

Look at the image. Decide if a human roughly hand-drew "{target}".
Imperfect strokes OK. Reject blank, wrong chars, or typed/screenshot text.

End your reply with ONE JSON object (no markdown):
{{"match":true,"human_like":true,"read_as":"{target}","reason":"ok"}}
or
{{"match":false,"human_like":false,"read_as":"","reason":"blank"}}
"""
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

    used_model = VISION_MODEL
    text = ""
    try:
        client = get_modal_client()
        response = client.chat.completions.create(
            model=VISION_MODEL,
            messages=messages,
            stream=False,
            max_tokens=2048,
            temperature=0.1,
            top_p=0.9,
            extra_body={"reasoning_effort": "high"},
        )
        text = _message_text(response.choices[0].message)
    except Exception as modal_err:
        # Fallback: Baseten Muse Spark Open (multimodal) if Modal is down/unconfigured
        try:
            used_model = DEFAULT_MODEL
            response = get_client().chat.completions.create(
                model=DEFAULT_MODEL,
                messages=messages,
                stream=False,
                max_tokens=2200,
                temperature=0.1,
            )
            text = _message_text(response.choices[0].message)
        except Exception as baseten_err:
            return {
                "ok": False,
                "reason": f"vision unavailable (modal: {modal_err}; baseten: {baseten_err})",
                "model": VISION_MODEL,
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
                "model": used_model,
            }
    if not isinstance(data, dict):
        return {"ok": False, "reason": "invalid vision response", "model": used_model}

    match = bool(data.get("match"))
    human_like = bool(data.get("human_like", True))
    read_as = str(data.get("read_as") or "").strip().upper().replace(" ", "")
    reason = str(data.get("reason") or "")[:200]
    if not match and read_as == target:
        match = True
    ok = match
    return {
        "ok": ok,
        "match": match,
        "human_like": human_like,
        "read_as": read_as,
        "reason": reason,
        "model": used_model,
    }
