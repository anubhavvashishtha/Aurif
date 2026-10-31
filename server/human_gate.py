"""Human CAPTCHA: draw letters/numbers; vision model verifies the sketch."""

from __future__ import annotations

import base64
import io
import os
import secrets
import time
from typing import Any

# challenge_id -> { target, expires_at, kind, attempts }
_challenges: dict[str, dict[str, Any]] = {}
# token -> expires_at
_human_sessions: dict[str, float] = {}

CHALLENGE_TTL = 10 * 60
HUMAN_TTL = 12 * 60 * 60
COOKIE_NAME = "aurif_human"
# One submit plus the single redraw the failure copy promises.
MAX_CHALLENGE_ATTEMPTS = 2
# Demo shortcut. Off unless this flag is explicitly truthy.
BYPASS_ENV = "AURIF_ALLOW_HUMAN_BYPASS"
_BYPASS_TRUTHY = {"1", "true", "yes", "on"}

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


def _challenge_image(target: str) -> str:
    """Distorted PNG of the answer. The plaintext target never leaves the server."""
    from PIL import Image, ImageDraw, ImageFont

    rng = secrets.SystemRandom()
    width = 36 + 42 * max(1, len(target))
    height = 84
    img = Image.new("RGB", (width, height), (250, 250, 248))
    draw = ImageDraw.Draw(img)
    for _ in range(8):
        draw.line(
            [
                (rng.randrange(width), rng.randrange(height)),
                (rng.randrange(width), rng.randrange(height)),
            ],
            fill=(170 + rng.randrange(40), 170, 160),
            width=1,
        )
    font = ImageFont.load_default()
    glyph = Image.new("RGB", (max(8, len(target) * 14), 22), (250, 250, 248))
    ImageDraw.Draw(glyph).text((1, 1), target, fill=(25, 25, 25), font=font)
    glyph = glyph.resize((max(24, len(target) * 36), 52), Image.Resampling.NEAREST)
    img.paste(glyph, (10 + rng.randrange(6), 12 + rng.randrange(8)))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def issue_challenge() -> dict[str, Any]:
    target, kind = _random_target()
    challenge_id = secrets.token_urlsafe(16)
    _challenges[challenge_id] = {
        "target": target,
        "kind": kind,
        "attempts": 0,
        "expires_at": time.time() + CHALLENGE_TTL,
    }
    _prune()
    # Prompt stays generic. Humans read the image; agents must not get the answer.
    return {
        "challenge_id": challenge_id,
        "type": "draw",
        "kind": kind,
        "prompt": "Draw the characters shown above by hand on the pad below.",
        "image": _challenge_image(target),
        "hint": (
            "Sketch with your mouse or finger. Imperfect handwriting is fine. "
            "AI agents should use Aurif /ai/* instead of this storefront."
        ),
        "expires_in": CHALLENGE_TTL,
        "attempts_remaining": MAX_CHALLENGE_ATTEMPTS,
    }


def register_failed_attempt(challenge_id: str) -> str:
    """Count a wrong drawing. Returns ``retry`` or ``exhausted``.

    The challenge stays valid for one redraw, then it is consumed.
    """
    _prune()
    cid = (challenge_id or "").strip()
    row = _challenges.get(cid)
    if not row or row["expires_at"] < time.time():
        return "exhausted"
    row["attempts"] = int(row.get("attempts") or 0) + 1
    if row["attempts"] >= MAX_CHALLENGE_ATTEMPTS:
        _challenges.pop(cid, None)
        return "exhausted"
    return "retry"


def bypass_enabled() -> bool:
    """Literal ``bypass`` token. Disabled unless AURIF_ALLOW_HUMAN_BYPASS is set."""
    return os.environ.get(BYPASS_ENV, "").strip().lower() in _BYPASS_TRUTHY


def human_access_granted(token: str | None, *, required: bool) -> bool:
    """Whether this caller may pass the human storefront gate."""
    if not required:
        return True
    if human_session_valid(token):
        return True
    if bypass_enabled() and (token or "") == "bypass":
        return True
    return False


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


def answer_matches(target: str, answer: str) -> bool:
    """Typed fallback: same characters, ignoring spaces and case."""

    def norm(value: str) -> str:
        return "".join(ch for ch in (value or "").upper() if ch.isalnum())

    expected = norm(target)
    given = norm(answer)
    return bool(expected) and expected == given


def drawing_has_ink(image_data_url: str) -> bool:
    """True when a sketch has real strokes, not a blank canvas.

    Used only after the vision model is unavailable, so a human on the existing
    drawing pad can still enter the storefront.
    """
    import base64
    from io import BytesIO

    from PIL import Image

    raw_url = (image_data_url or "").strip()
    if not raw_url.startswith("data:image/"):
        return False
    _, _, b64 = raw_url.partition(",")
    if not b64:
        return False
    try:
        blob = base64.b64decode(b64, validate=False)
    except Exception:
        return False
    if len(blob) < 32:
        return False
    try:
        image = Image.open(BytesIO(blob)).convert("L")
    except Exception:
        return False
    image.thumbnail((160, 160))
    pixels = image.get_flattened_data() if hasattr(image, "get_flattened_data") else image.getdata()
    ink = sum(1 for pixel in pixels if pixel < 220)
    return ink >= 24


def _prune() -> None:
    now = time.time()
    for cid in [k for k, v in _challenges.items() if v["expires_at"] < now]:
        _challenges.pop(cid, None)
    for tok in [k for k, v in _human_sessions.items() if v < now]:
        _human_sessions.pop(tok, None)
