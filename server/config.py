"""Process settings for local `python app.py` and a hosted gunicorn process.

Defaults match a zero-config checkout: bind 127.0.0.1:8787 with the Werkzeug
debugger on, CORS limited to the two local frontends, public URLs pointing at
those same ports. Hosted deploys set the variables documented in DEPLOY.md.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = Path(__file__).resolve().parent

# Do not override variables the platform or shell already set. muse_client
# still reloads the repo-root .env with override=True for model keys.
load_dotenv(ROOT / ".env", override=False)
load_dotenv(SERVER_DIR / ".env", override=False)

_LOCAL_ORIGINS = (
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
    "http://localhost:5173",
    "http://localhost:5174",
)

_TRUTHY = {"1", "true", "yes", "on"}
_FALSY = {"0", "false", "no", "off"}


def _raw(name: str) -> str:
    return os.environ.get(name, "").strip()


def _first(*names: str) -> str:
    for name in names:
        value = _raw(name)
        if value:
            return value
    return ""


def port() -> int:
    raw = _raw("PORT") or "8787"
    try:
        value = int(raw)
    except ValueError:
        return 8787
    if not 1 <= value <= 65535:
        return 8787
    return value


def bind_host() -> str:
    """Host for `python app.py`. Gunicorn uses its own --bind.

    Local zero-config stays on the loopback. A platform-injected PORT (Render,
    Railway) binds all interfaces so the process is reachable in the container.
    """
    explicit = _raw("HOST")
    if explicit:
        return explicit
    if _raw("PORT"):
        return "0.0.0.0"
    return "127.0.0.1"


def flask_debug() -> bool:
    """Werkzeug debugger / reloader. Off in production.

    Explicit FLASK_DEBUG or DEBUG wins. Otherwise production is when
    AURIF_ENV=production or a platform set PORT. A laptop `python app.py`
    with no env still runs debug, matching the previous hardcoded default.
    """
    for name in ("FLASK_DEBUG", "DEBUG"):
        raw = os.environ.get(name)
        if raw is None or not raw.strip():
            continue
        value = raw.strip().lower()
        if value in _TRUTHY:
            return True
        if value in _FALSY:
            return False
    if _raw("AURIF_ENV").lower() in ("production", "prod"):
        return False
    if _raw("PORT"):
        return False
    return True


def api_public_url() -> str:
    """Origin advertised to browsers and used when the server calls itself."""
    explicit = _first("AURIF_API_PUBLIC_URL", "API_BASE")
    if explicit:
        return explicit.rstrip("/")
    return f"http://127.0.0.1:{port()}"


def customer_site_url() -> str:
    return (_first("CUSTOMER_SITE_URL", "STOREFRONT_URL") or "http://127.0.0.1:5173").rstrip("/")


def dashboard_url() -> str:
    return (_first("DASHBOARD_URL") or "http://127.0.0.1:5174").rstrip("/")


def pinned_site_key() -> str:
    """Stable demo site key. Applied only when store.json is first created."""
    return _raw("AURIF_SITE_KEY")


def store_path() -> Path:
    override = _raw("AURIF_STORE_PATH")
    if override:
        return Path(override)
    return SERVER_DIR / "data" / "store.json"


def _as_origin(value: str) -> str | None:
    raw = value.strip()
    if not raw or raw == "*":
        return None
    if "://" not in raw:
        return raw.rstrip("/") or None
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def cors_origins() -> list[str]:
    """Explicit browser origins. `*` is ignored so production cannot go wildcard.

    Local dev origins stay listed so a laptop checkout works with no env.
    AURIF_CORS_ORIGINS / CORS_ORIGINS and the public frontend URLs are added
    on top. That is how the deployed Vercel apps are allowed.
    """
    configured = _first("AURIF_CORS_ORIGINS", "CORS_ORIGINS")
    if configured and any(part.strip() == "*" for part in configured.split(",")):
        print(
            "Refusing CORS origin '*'. Set AURIF_CORS_ORIGINS to explicit origins.",
            file=sys.stderr,
        )

    found: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        origin = _as_origin(value)
        if origin and origin not in seen:
            seen.add(origin)
            found.append(origin)

    for origin in _LOCAL_ORIGINS:
        add(origin)
    for part in configured.split(","):
        add(part)
    add(customer_site_url())
    add(dashboard_url())
    return found
