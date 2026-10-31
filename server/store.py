"""JSON-backed store for owners, sites, endpoint policy, and agent activity."""

from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import config
from endpoints_default import DEFAULT_ENDPOINTS, ensure_endpoint_shape

STORE_PATH = config.store_path()
DATA_DIR = STORE_PATH.parent
_lock = threading.RLock()


def _hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000
    ).hex()
    return salt, digest


def _verify_password(password: str, salt: str, digest: str) -> bool:
    _, check = _hash_password(password, salt)
    return secrets.compare_digest(check, digest)


def _empty() -> dict[str, Any]:
    return {
        "users": {},
        "owner_sessions": {},
        "sites": {},
        "activity": [],
    }


def _seed(data: dict[str, Any]) -> dict[str, Any]:
    if data.get("users"):
        return data

    salt, digest = _hash_password("demo1234")
    owner_id = str(uuid.uuid4())
    site_id = "demo-shop"
    data["users"][owner_id] = {
        "id": owner_id,
        "email": "owner@aurif.dev",
        "name": "Demo Owner",
        "salt": salt,
        "password_hash": digest,
        "created_at": time.time(),
    }
    data["sites"][site_id] = {
        "id": site_id,
        "owner_id": owner_id,
        "name": "Northline Goods",
        "url": config.customer_site_url(),
        "site_key": config.pinned_site_key() or secrets.token_urlsafe(18),
        "agent_welcome": "You are browsing Northline Goods via permissioned AI access.",
        "blocked_agents": ["blocked"],
        "block_anonymous_agents": True,
        "require_human_captcha": True,
        "endpoints": deepcopy(DEFAULT_ENDPOINTS),
        "created_at": time.time(),
    }
    return data


def _migrate(data: dict[str, Any]) -> bool:
    changed = False
    for site in data.get("sites", {}).values():
        if "block_anonymous_agents" not in site:
            site["block_anonymous_agents"] = True
            changed = True
        if "require_human_captcha" not in site:
            site["require_human_captcha"] = True
            changed = True
        eps = site.get("endpoints") or []
        needs = not eps or not eps[0].get("response_fields")
        ids = {str(e.get("id", "")) for e in eps}
        home = next((e for e in eps if e.get("id") == "page.home"), None)
        shop = next((e for e in eps if e.get("id") == "page.products"), None)
        home_keys = {f.get("key") for f in (home or {}).get("response_fields") or [] if isinstance(f, dict)}
        shop_keys = {f.get("key") for f in (shop or {}).get("response_fields") or [] if isinstance(f, dict)}
        # Migrate widget leftovers, per-product rows, and pre–page-type schemas.
        # Shop element prices were added later; refresh so owners can see that toggle.
        legacy = any(
            (e.get("path") or "").endswith("/widget")
            or (e.get("action_id") or "").endswith(":widget")
            or str(e.get("id", "")).endswith(".widget")
            or str(e.get("id", "")).startswith("page.product.")
            or str(e.get("id", "")).startswith("action.product.add.")
            or str(e.get("id", "")).startswith("action.product.view.")
            for e in eps
        ) or (
            bool(eps)
            and (
                "page.product" not in ids
                or "meta.products" not in shop_keys
                or "elements[].meta.price" not in shop_keys
                or bool(home_keys & {"meta.price", "rating", "discount", "reviews"})
            )
        )
        if needs or legacy:
            site["endpoints"] = ensure_endpoint_shape(eps)
            site["name"] = site.get("name") or "Northline Goods"
            if "127.0.0.1:8787" in (site.get("url") or ""):
                site["url"] = config.customer_site_url()
            changed = True
    return changed


def load() -> dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with _lock:
        if STORE_PATH.exists():
            data = json.loads(STORE_PATH.read_text(encoding="utf-8"))
            if _migrate(data):
                _write(data)
        else:
            data = _seed(_empty())
            _write(data)
        return data


def _write(data: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STORE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(STORE_PATH)


def save(mutator) -> dict[str, Any]:
    with _lock:
        data = load()
        mutator(data)
        _write(data)
        return data


def public_site(site: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": site["id"],
        "name": site["name"],
        "url": site.get("url", ""),
        "site_key": site["site_key"],
        "agent_welcome": site.get("agent_welcome", ""),
        "blocked_agents": site.get("blocked_agents", []),
        "block_anonymous_agents": bool(site.get("block_anonymous_agents", True)),
        "require_human_captcha": bool(site.get("require_human_captcha", True)),
        "endpoints": site.get("endpoints", []),
        "created_at": site.get("created_at"),
    }


def find_user_by_email(email: str) -> dict[str, Any] | None:
    email = email.strip().lower()
    data = load()
    for user in data["users"].values():
        if user["email"].lower() == email:
            return user
    return None


def create_user(email: str, password: str, name: str) -> dict[str, Any]:
    email = email.strip().lower()
    if find_user_by_email(email):
        raise ValueError("email already registered")
    if len(password) < 6:
        raise ValueError("password must be at least 6 characters")

    salt, digest = _hash_password(password)
    user_id = str(uuid.uuid4())

    def mut(data: dict[str, Any]) -> None:
        data["users"][user_id] = {
            "id": user_id,
            "email": email,
            "name": name.strip() or email.split("@")[0],
            "salt": salt,
            "password_hash": digest,
            "created_at": time.time(),
        }

    save(mut)
    return find_user_by_email(email)  # type: ignore


def authenticate(email: str, password: str) -> dict[str, Any] | None:
    user = find_user_by_email(email)
    if not user:
        return None
    if not _verify_password(password, user["salt"], user["password_hash"]):
        return None
    return user


def create_owner_session(user_id: str) -> str:
    token = secrets.token_urlsafe(24)

    def mut(data: dict[str, Any]) -> None:
        data["owner_sessions"][token] = {
            "user_id": user_id,
            "created_at": time.time(),
            "expires_at": time.time() + 60 * 60 * 24 * 7,
        }

    save(mut)
    return token


def get_owner_session(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    data = load()
    session = data["owner_sessions"].get(token)
    if not session:
        return None
    if session["expires_at"] < time.time():
        def mut(d: dict[str, Any]) -> None:
            d["owner_sessions"].pop(token, None)

        save(mut)
        return None
    user = data["users"].get(session["user_id"])
    if not user:
        return None
    return {"token": token, "user": user}


def logout_owner(token: str | None) -> None:
    if not token:
        return

    def mut(data: dict[str, Any]) -> None:
        data["owner_sessions"].pop(token, None)

    save(mut)


def sites_for_owner(owner_id: str) -> list[dict[str, Any]]:
    data = load()
    return [
        public_site(s)
        for s in data["sites"].values()
        if s.get("owner_id") == owner_id
    ]


def get_site(site_id: str) -> dict[str, Any] | None:
    return load()["sites"].get(site_id)


def create_site(owner_id: str, name: str, url: str) -> dict[str, Any]:
    site_id = "site-" + secrets.token_hex(4)

    def mut(data: dict[str, Any]) -> None:
        data["sites"][site_id] = {
            "id": site_id,
            "owner_id": owner_id,
            "name": name.strip() or "Untitled site",
            "url": url.strip() or "",
            "site_key": secrets.token_urlsafe(18),
            "agent_welcome": "AI agents: you have permissioned access.",
            "blocked_agents": [],
            "block_anonymous_agents": True,
            "require_human_captcha": True,
            "endpoints": deepcopy(DEFAULT_ENDPOINTS),
            "created_at": time.time(),
        }

    save(mut)
    return public_site(get_site(site_id))  # type: ignore


def update_site(site_id: str, owner_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    site = get_site(site_id)
    if not site or site["owner_id"] != owner_id:
        raise PermissionError("site not found")

    def mut(data: dict[str, Any]) -> None:
        s = data["sites"][site_id]
        if "name" in patch and isinstance(patch["name"], str):
            s["name"] = patch["name"].strip() or s["name"]
        if "url" in patch and isinstance(patch["url"], str):
            s["url"] = patch["url"].strip()
        if "agent_welcome" in patch and isinstance(patch["agent_welcome"], str):
            s["agent_welcome"] = patch["agent_welcome"]
        if "blocked_agents" in patch and isinstance(patch["blocked_agents"], list):
            s["blocked_agents"] = [
                str(a).strip() for a in patch["blocked_agents"] if str(a).strip()
            ]
        if "block_anonymous_agents" in patch:
            s["block_anonymous_agents"] = bool(patch["block_anonymous_agents"])
        if "require_human_captcha" in patch:
            s["require_human_captcha"] = bool(patch["require_human_captcha"])
        if patch.get("rotate_site_key"):
            s["site_key"] = secrets.token_urlsafe(18)
        if "endpoints" in patch and isinstance(patch["endpoints"], list):
            by_id = {e["id"]: e for e in s.get("endpoints", [])}
            for item in patch["endpoints"]:
                eid = item.get("id")
                if eid not in by_id:
                    continue
                if "agent_access" in item:
                    by_id[eid]["agent_access"] = bool(item["agent_access"])
                if "response_fields" in item and isinstance(item["response_fields"], list):
                    vis = {
                        f.get("key"): f.get("agent_visible", True)
                        for f in item["response_fields"]
                        if isinstance(f, dict)
                    }
                    for f in by_id[eid].get("response_fields", []):
                        if f.get("key") in vis:
                            f["agent_visible"] = bool(vis[f["key"]])
                if "request_fields" in item and isinstance(item["request_fields"], list):
                    allowed = {
                        f.get("key"): f.get("agent_allowed", True)
                        for f in item["request_fields"]
                        if isinstance(f, dict)
                    }
                    for f in by_id[eid].get("request_fields", []):
                        if f.get("key") in allowed:
                            f["agent_allowed"] = bool(allowed[f["key"]])
            s["endpoints"] = list(by_id.values())

    save(mut)
    return public_site(get_site(site_id))  # type: ignore


def set_endpoint_access(site_id: str, owner_id: str, endpoint_id: str, allowed: bool) -> dict[str, Any]:
    return update_site(site_id, owner_id, {"endpoints": [{"id": endpoint_id, "agent_access": allowed}]})


def set_endpoint_fields(
    site_id: str,
    owner_id: str,
    endpoint_id: str,
    *,
    response_fields: list[dict[str, Any]] | None = None,
    request_fields: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    patch: dict[str, Any] = {"id": endpoint_id}
    if response_fields is not None:
        patch["response_fields"] = response_fields
    if request_fields is not None:
        patch["request_fields"] = request_fields
    return update_site(site_id, owner_id, {"endpoints": [patch]})


def canonical_ai_path(raw: str | None) -> str:
    """Collapse an agent path to one canonical form.

    Duplicate slashes, dot segments, percent-encoding, and case differences
    all land on one path. Which of those paths an agent may open is decided
    later, from the site's configured page endpoints — not from a fixed list.
    """
    text = unquote(str("/" if raw is None else raw))
    text = text.replace("\\", "/").replace("\x00", "").strip()
    if not text:
        return "/"
    text = text.split("?", 1)[0].split("#", 1)[0].strip()
    if not text:
        return "/"
    if not text.startswith("/"):
        text = "/" + text
    parts: list[str] = []
    for part in text.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    path = "/" + "/".join(parts)
    path = path.lower()
    if path in ("/index.html", "/index.htm"):
        return "/"
    return path


def canonical_page_pattern(pattern: str | None) -> str:
    """Normalize an owner-configured page path, keeping a trailing ``/*`` wildcard."""
    text = str(pattern or "").strip()
    if not text:
        return ""
    if text.endswith("/*"):
        base = canonical_ai_path(text[:-2] or "/")
        if base == "/":
            return "/*"
        return base.rstrip("/") + "/*"
    return canonical_ai_path(text)


def capture_wildcard(pattern: str | None, path: str | None) -> str | None:
    """Return the single path segment captured by a configured ``/*`` pattern."""
    pattern = canonical_page_pattern(pattern)
    path = canonical_ai_path(path)
    if not pattern.endswith("/*"):
        return None
    prefix = pattern[:-1]
    if not path.startswith(prefix):
        return None
    rest = path[len(prefix) :]
    if not rest or "/" in rest:
        return None
    return rest


def page_decision(site: dict[str, Any], raw: str | None) -> tuple[str, str]:
    """Return ``(canonical_path, decision)`` where decision is allow, closed, or unmapped.

    The allow set is that site's page endpoints (the same rows the dashboard
    toggles). A path that matches none of them is denied.
    """
    path = canonical_ai_path(raw)
    ep = find_endpoint(site, path=path)
    if ep is None:
        return path, "unmapped"
    if not bool(ep.get("agent_access", True)):
        return path, "closed"
    return path, "allow"


def _path_matches(pattern: str, path: str) -> bool:
    """Exact or single-segment wildcard from the site's own page patterns."""
    pattern = canonical_page_pattern(pattern)
    path = canonical_ai_path(path)
    if not pattern or not path:
        return False
    if pattern == path:
        return True
    if pattern.endswith("/*"):
        return capture_wildcard(pattern, path) is not None
    return False


def _action_matches(pattern: str, action_id: str) -> bool:
    """Exact or suffix wildcard: `product.add:*` → `product.add:field-tote`."""
    if not pattern or not action_id:
        return False
    if pattern == action_id:
        return True
    if pattern.endswith(":*"):
        prefix = pattern[:-1]  # product.add:
        return action_id.startswith(prefix) and len(action_id) > len(prefix)
    return False


def find_endpoint(site: dict[str, Any], *, path: str | None = None, action_id: str | None = None) -> dict[str, Any] | None:
    """Resolve page/action endpoint. Exact match wins, then wildcard patterns."""
    if path is not None:
        path = canonical_ai_path(path)
    pattern_hit: dict[str, Any] | None = None
    for ep in site.get("endpoints") or []:
        if path is not None and ep.get("kind") == "page":
            ep_path = canonical_page_pattern(ep.get("path") or "")
            if not ep_path:
                continue
            if not ep_path.endswith("/*") and ep_path == path:
                return ep
            if pattern_hit is None and _path_matches(ep_path, path):
                pattern_hit = ep
        if action_id is not None and ep.get("kind") == "action":
            ep_aid = ep.get("action_id") or ""
            if ep_aid == action_id:
                return ep
            if pattern_hit is None and _action_matches(ep_aid, action_id):
                pattern_hit = ep
    return pattern_hit


def endpoint_allowed(site: dict[str, Any], *, path: str | None = None, action_id: str | None = None) -> bool:
    if path is not None:
        # Unmapped paths are denied. A miss used to allow the request, which
        # let /products/x/<slug> skip the product-page policy.
        _, decision = page_decision(site, path)
        return decision == "allow"
    if action_id is not None:
        ep = find_endpoint(site, action_id=action_id)
        if ep is None:
            return True
        return bool(ep.get("agent_access", True))
    return True


def log_activity(
    site_id: str,
    *,
    kind: str,
    agent_id: str | None,
    path: str | None = None,
    action_id: str | None = None,
    detail: dict[str, Any] | None = None,
    session_token: str | None = None,
) -> None:
    event = {
        "id": str(uuid.uuid4()),
        "ts": time.time(),
        "site_id": site_id,
        "kind": kind,
        "agent_id": agent_id,
        "path": path,
        "action_id": action_id,
        "detail": detail or {},
        "session": (session_token[:8] + "…") if session_token else None,
    }

    def mut(data: dict[str, Any]) -> None:
        data["activity"].append(event)
        if len(data["activity"]) > 2000:
            data["activity"] = data["activity"][-2000:]

    save(mut)


def activity_for_site(site_id: str, limit: int = 200) -> list[dict[str, Any]]:
    data = load()
    events = [e for e in data["activity"] if e.get("site_id") == site_id]
    return list(reversed(events[-limit:]))


# Ensure seed exists on import
load()
