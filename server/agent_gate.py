"""Detect anonymous / non-browser agent traffic for demo enforcement."""

from __future__ import annotations

from typing import Any

# Obvious automation / AI crawler signals (demo-grade, not adversarial-proof).
BOT_UA_HINTS = (
    "curl/",
    "wget/",
    "python-requests",
    "python-urllib",
    "httpx",
    "aiohttp",
    "scrapy",
    "go-http-client",
    "headlesschrome",
    "headless",
    "playwright",
    "puppeteer",
    "selenium",
    "phantomjs",
    "gptbot",
    "chatgpt",
    "claudebot",
    "anthropic",
    "openai",
    "bytespider",
    "ccbot",
    "perplexitybot",
    "diffbot",
    "node-fetch",
    "undici",
)


def looks_like_anonymous_agent(headers: dict[str, str] | Any) -> bool:
    """
    True when the caller looks like an automated agent without a human browser.
    Pass Flask request.headers or a plain dict (case-insensitive keys).
    """
    def get(name: str) -> str:
        if hasattr(headers, "get"):
            # Flask EnvironHeaders is case-insensitive
            val = headers.get(name) or headers.get(name.lower()) or headers.get(name.title())
            return (val or "").strip()
        return ""

    # Explicit demo override — easiest way to prove the gate in demos.
    if get("X-Demo-As-Agent") in ("1", "true", "yes"):
        return True

    # Declared Aurif agent without a session must go through handshake first
    # (session is checked by the caller).
    if get("X-Aurif-Agent") and not get("X-Aurif-Session"):
        return True

    ua = get("User-Agent").lower()
    if not ua:
        return True
    if any(h in ua for h in BOT_UA_HINTS):
        return True

    return False


def blocked_response_body(site_name: str = "this site") -> dict[str, Any]:
    return {
        "ok": False,
        "error": "anonymous_agent_blocked",
        "message": (
            f"Automated access to {site_name} is blocked. "
            "AI agents must identify via Aurif: GET /.well-known/aurif.json "
            "then POST /ai/handshake, then use /ai/page and /ai/actions."
        ),
        "aurif": {
            "well_known": "/.well-known/aurif.json",
            "handshake": "/ai/handshake",
        },
    }
