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

DATA_DIR = Path(__file__).resolve().parent / "data"
STORE_PATH = DATA_DIR / "store.json"
_lock = threading.RLock()

DEFAULT_ENDPOINTS = [
    {
        "id": "page.home",
        "label": "Home page",
        "kind": "page",
        "path": "/",
        "agent_access": True,
    },
    {
        "id": "page.products",
        "label": "Products list",
        "kind": "page",
        "path": "/products",
        "agent_access": True,
    },
    {
        "id": "page.product.widget",
        "label": "Product: Field Tote",
        "kind": "page",
        "path": "/products/widget",
        "agent_access": True,
    },
    {
        "id": "page.product.badge",
        "label": "Product: Trail Notebook",
        "kind": "page",
        "path": "/products/badge",
        "agent_access": True,
    },
    {
        "id": "page.cart",
        "label": "Cart page",
        "kind": "page",
        "path": "/cart",
        "agent_access": True,
    },
    {
        "id": "action.nav.products",
        "label": "Action: Shop",
        "kind": "action",
        "action_id": "nav.products",
        "agent_access": True,
    },
    {
        "id": "action.nav.cart",
        "label": "Action: Cart",
        "kind": "action",
        "action_id": "nav.cart",
        "agent_access": True,
    },
    {
        "id": "action.nav.home",
        "label": "Action: Home",
        "kind": "action",
        "action_id": "nav.home",
        "agent_access": True,
    },
    {
        "id": "action.product.add.widget",
        "label": "Action: Add Field Tote",
        "kind": "action",
        "action_id": "product.add:widget",
        "agent_access": True,
    },
    {
        "id": "action.product.add.badge",
        "label": "Action: Add Trail Notebook",
        "kind": "action",
        "action_id": "product.add:badge",
        "agent_access": True,
    },
    {
        "id": "action.product.view.widget",
        "label": "Action: View Field Tote",
        "kind": "action",
        "action_id": "product.view:widget",
        "agent_access": True,
    },
    {
        "id": "action.product.view.badge",
        "label": "Action: View Trail Notebook",
        "kind": "action",
        "action_id": "product.view:badge",
        "agent_access": True,
    },
    {
        "id": "action.cart.clear",
        "label": "Action: Clear cart",
        "kind": "action",
        "action_id": "cart.clear",
        "agent_access": True,
    },
    {
        "id": "action.cart.checkout",
        "label": "Action: Checkout",
        "kind": "action",
        "action_id": "cart.checkout",
        "agent_access": True,
    },
]


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
        "url": "http://127.0.0.1:8787",
        "site_key": secrets.token_urlsafe(18),
        "agent_welcome": "You are browsing Northline Goods via permissioned AI access.",
        "blocked_agents": ["blocked"],
        "endpoints": deepcopy(DEFAULT_ENDPOINTS),
        "created_at": time.time(),
    }
    return data


def load() -> dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with _lock:
        if STORE_PATH.exists():
            data = json.loads(STORE_PATH.read_text(encoding="utf-8"))
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
        if patch.get("rotate_site_key"):
            s["site_key"] = secrets.token_urlsafe(18)
        if "endpoints" in patch and isinstance(patch["endpoints"], list):
            by_id = {e["id"]: e for e in s.get("endpoints", [])}
            for item in patch["endpoints"]:
                eid = item.get("id")
                if eid in by_id and "agent_access" in item:
                    by_id[eid]["agent_access"] = bool(item["agent_access"])
            s["endpoints"] = list(by_id.values())

    save(mut)
    return public_site(get_site(site_id))  # type: ignore


def set_endpoint_access(site_id: str, owner_id: str, endpoint_id: str, allowed: bool) -> dict[str, Any]:
    return update_site(site_id, owner_id, {"endpoints": [{"id": endpoint_id, "agent_access": allowed}]})


def endpoint_allowed(site: dict[str, Any], *, path: str | None = None, action_id: str | None = None) -> bool:
    endpoints = site.get("endpoints") or []
    if path is not None:
        norm = path if path.startswith("/") else "/" + path
        if norm != "/" and norm.endswith("/"):
            norm = norm.rstrip("/")
        for ep in endpoints:
            if ep.get("kind") == "page" and ep.get("path") == norm:
                return bool(ep.get("agent_access", True))
        # product detail fallback: unknown paths default allow unless explicitly listed
        return True
    if action_id is not None:
        for ep in endpoints:
            if ep.get("kind") == "action" and ep.get("action_id") == action_id:
                return bool(ep.get("agent_access", True))
        return True
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
