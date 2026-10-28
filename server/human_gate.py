"""Human CAPTCHA: draw letters/numbers; vision model verifies the sketch."""

from __future__ import annotations

import secrets
import time
from typing import Any

# challenge_id -> { target, expires_at, kind }
_challenges: dict[str, dict[str, Any]] = {}
# token -> expires_at
_human_sessions: dict[str, float] = {}

CHALLENGE_TTL = 10 * 60
HUMAN_TTL = 12 * 60 * 60
COOKIE_NAME = "aurif_human"

# Avoid ambiguous lookalikes in the prompt (0/O, 1/I/l)
_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"
_DIGITS = "23456789"


def _random_target() -> tuple[str, str]:
    """Return (target, kind) — kind is letter | digit | code."""
    mode = secrets.randbelow(3)
    if mode == 0:
        return secrets.choice(_LETTERS), "letter"
    if mode == 1:
        return secrets.choice(_DIGITS), "digit"
    # 2–3 char mix
    n = 2 + secrets.randbelow(2)
    alphabet = _LETTERS + _DIGITS
    target = "".join(secrets.choice(alphabet) for _ in range(n))
    return target, "code"


def issue_challenge() -> dict[str, Any]:
    target, kind = _random_target()
    challenge_id = secrets.token_urlsafe(16)
    _challenges[challenge_id] = {
        "target": target,
        "kind": kind,
        "expires_at": time.time() + CHALLENGE_TTL,
    }
    _prune()
    if kind == "letter":
        prompt = f'Draw the letter "{target}" by hand on the pad below.'
    elif kind == "digit":
        prompt = f'Draw the number "{target}" by hand on the pad below.'
    else:
        prompt = f'Draw these characters by hand: {target}'
    return {
        "challenge_id": challenge_id,
        "type": "draw",
        "kind": kind,
        "target": target,
        "prompt": prompt,
        "hint": (
            "Sketch with your mouse or finger. Imperfect handwriting is fine. "
            "AI agents should use Aurif /ai/* instead of this storefront."
        ),
        "expires_in": CHALLENGE_TTL,
    }


def peek_challenge(challenge_id: str) -> dict[str, Any] | None:
    _prune()
    row = _challenges.get((challenge_id or "").strip())
    if not row or row["expires_at"] < time.time():
        return None
    return row


def consume_challenge(challenge_id: str) -> dict[str, Any] | None:
    _prune()
    return _challenges.pop((challenge_id or "").strip(), None)


def issue_human_token() -> str:
    token = secrets.token_urlsafe(24)
    _human_sessions[token] = time.time() + HUMAN_TTL
    return token


def verify_challenge(challenge_id: str, answer: str) -> str | None:
    """Legacy math path — disabled; drawing CAPTCHA uses vision verify."""
    _ = challenge_id, answer
    return None


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
