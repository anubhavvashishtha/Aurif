"""Demo human CAPTCHA: challenge + short-lived human session tokens."""

from __future__ import annotations

import secrets
import time
from typing import Any

# challenge_id -> { answer, expires_at }
_challenges: dict[str, dict[str, Any]] = {}
# token -> expires_at
_human_sessions: dict[str, float] = {}

CHALLENGE_TTL = 10 * 60
HUMAN_TTL = 12 * 60 * 60
COOKIE_NAME = "aurif_human"


def issue_challenge() -> dict[str, Any]:
    a = secrets.randbelow(8) + 2
    b = secrets.randbelow(8) + 2
    challenge_id = secrets.token_urlsafe(16)
    _challenges[challenge_id] = {
        "answer": str(a + b),
        "expires_at": time.time() + CHALLENGE_TTL,
    }
    _prune()
    return {
        "challenge_id": challenge_id,
        "prompt": f"What is {a} + {b}?",
        "hint": "Solve this to prove you are human. AI agents should use Aurif /ai/* instead.",
        "expires_in": CHALLENGE_TTL,
    }


def verify_challenge(challenge_id: str, answer: str) -> str | None:
    _prune()
    row = _challenges.pop((challenge_id or "").strip(), None)
    if not row or row["expires_at"] < time.time():
        return None
    if str(answer).strip() != str(row["answer"]):
        return None
    token = secrets.token_urlsafe(24)
    _human_sessions[token] = time.time() + HUMAN_TTL
    return token


def human_session_valid(token: str | None) -> bool:
    if not token:
        return False
    _prune()
    exp = _human_sessions.get(token)
    if not exp:
        return False
    if exp < time.time():
        _human_sessions.pop(token, None)
        return False
    return True


def _prune() -> None:
    now = time.time()
    for cid in [k for k, v in _challenges.items() if v["expires_at"] < now]:
        _challenges.pop(cid, None)
    for tok in [k for k, v in _human_sessions.items() if v < now]:
        _human_sessions.pop(tok, None)
