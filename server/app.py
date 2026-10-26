"""
Aurif — demo shop + AI protocol + owner dashboard APIs.
"""

from __future__ import annotations

import secrets
import time
import uuid
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request, send_from_directory

import store

ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = ROOT / "demo"
SDK_DIR = ROOT / "sdk"
DASH_DIR = ROOT / "dashboard"

PROTOCOL = "aurif-1"
DEFAULT_SITE_ID = "demo-shop"
SESSION_TTL = 3600
ALLOWED_SCOPES = ("view", "act")

app = Flask(__name__)

sessions: dict[str, dict[str, Any]] = {}
cart_by_session: dict[str, list[str]] = {}

PRODUCTS = {
    "widget": {
        "id": "widget",
        "name": "Field Tote",
        "price": 68,
        "summary": "Heavy canvas tote with a reinforced base and brass hardware.",
    },
    "badge": {
        "id": "badge",
        "name": "Trail Notebook",
        "price": 18,
        "summary": "Pocket-size ruled notebook with a waterproof cover.",
    },
}


def site_record() -> dict[str, Any]:
    site = store.get_site(DEFAULT_SITE_ID)
    if not site:
        store.load()
        site = store.get_site(DEFAULT_SITE_ID)
    assert site is not None
    return site


def owner_auth():
    token = request.headers.get("X-Aurif-Owner") or request.cookies.get("aurif_owner")
    session = store.get_owner_session(token)
    if not session:
        return None, (jsonify({"ok": False, "error": "login required"}), 401)
    return session, None


def get_agent_session() -> dict[str, Any] | None:
    token = request.headers.get("X-Aurif-Session")
    if not token:
        return None
    session = sessions.get(token)
    if not session:
        return None
    if session["expires_at"] < time.time():
        sessions.pop(token, None)
        return None
    return session


def require_agent_session(*scopes: str):
    session = get_agent_session()
    if not session:
        return None, (jsonify({"ok": False, "error": "missing or invalid session"}), 401)
    for scope in scopes:
        if scope not in session["scopes"]:
            return None, (
                jsonify({"ok": False, "error": f"scope '{scope}' not granted"}),
                403,
            )
    return session, None


def deny_page(path: str, reason: str) -> dict[str, Any]:
    site = site_record()
    return {
        "path": path,
        "title": site["name"],
        "summary": reason,
        "blocked": True,
        "elements": [],
    }


def page_snapshot(path: str, session: dict[str, Any]) -> dict[str, Any]:
    site = site_record()
    path = path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    if not store.endpoint_allowed(site, path=path):
        return deny_page(path, "This page endpoint is blocked for AI agents by the site owner.")

    cart = cart_by_session.setdefault(session["token"], [])
    welcome = site.get("agent_welcome") or ""

    def filter_elements(elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for el in elements:
            aid = el.get("action_id")
            if aid and not store.endpoint_allowed(site, action_id=aid):
                continue
            out.append(el)
        return out

    if path in ("/", "/index.html"):
        path = "/"
        return {
            "path": "/",
            "title": site["name"],
            "summary": welcome or "A small demo store for permissioned AI browsing.",
            "site_key_hint": site["site_key"][:6] + "…",
            "elements": filter_elements(
                [
                    {
                        "action_id": "nav.products",
                        "type": "link",
                        "label": "Shop",
                        "href": "/products",
                        "scopes": ["view"],
                    },
                    {
                        "action_id": "nav.cart",
                        "type": "link",
                        "label": f"Cart ({len(cart)})",
                        "href": "/cart",
                        "scopes": ["view"],
                    },
                    {
                        "action_id": "product.add:widget",
                        "type": "button",
                        "label": "Add Field Tote to cart",
                        "scopes": ["act"],
                    },
                ]
            ),
        }

    if path == "/products":
        elements: list[dict[str, Any]] = [
            {
                "action_id": "nav.home",
                "type": "link",
                "label": "Home",
                "href": "/",
                "scopes": ["view"],
            }
        ]
        for product in PRODUCTS.values():
            elements.append(
                {
                    "action_id": f"product.view:{product['id']}",
                    "type": "link",
                    "label": f"View {product['name']}",
                    "href": f"/products/{product['id']}",
                    "scopes": ["view"],
                    "meta": {"price": product["price"]},
                }
            )
            elements.append(
                {
                    "action_id": f"product.add:{product['id']}",
                    "type": "button",
                    "label": f"Add {product['name']} to cart",
                    "scopes": ["act"],
                }
            )
        return {
            "path": "/products",
            "title": "Shop — " + site["name"],
            "summary": f"{welcome} {len(PRODUCTS)} products available.".strip(),
            "elements": filter_elements(elements),
        }

    if path.startswith("/products/"):
        pid = path.split("/")[-1]
        product = PRODUCTS.get(pid)
        if not product:
            return {
                "path": path,
                "title": "Not found",
                "summary": "Unknown product.",
                "elements": filter_elements(
                    [
                        {
                            "action_id": "nav.products",
                            "type": "link",
                            "label": "Back to shop",
                            "href": "/products",
                            "scopes": ["view"],
                        }
                    ]
                ),
            }
        return {
            "path": f"/products/{pid}",
            "title": product["name"],
            "summary": f"{welcome} {product['summary']}".strip(),
            "elements": filter_elements(
                [
                    {
                        "action_id": "nav.products",
                        "type": "link",
                        "label": "Back to shop",
                        "href": "/products",
                        "scopes": ["view"],
                    },
                    {
                        "action_id": f"product.add:{pid}",
                        "type": "button",
                        "label": f"Add {product['name']} to cart",
                        "scopes": ["act"],
                    },
                ]
            ),
            "meta": product,
        }

    if path == "/cart":
        return {
            "path": "/cart",
            "title": "Cart — " + site["name"],
            "summary": f"{welcome} {len(cart)} item(s) in cart.".strip(),
            "elements": filter_elements(
                [
                    {
                        "action_id": "nav.products",
                        "type": "link",
                        "label": "Continue shopping",
                        "href": "/products",
                        "scopes": ["view"],
                    },
                    {
                        "action_id": "cart.clear",
                        "type": "button",
                        "label": "Clear cart",
                        "scopes": ["act"],
                    },
                    {
                        "action_id": "cart.checkout",
                        "type": "button",
                        "label": "Checkout (demo)",
                        "scopes": ["act"],
                    },
                ]
            ),
            "meta": {
                "items": cart,
                "products": [PRODUCTS[i] for i in cart if i in PRODUCTS],
            },
        }

    return {
        "path": path,
        "title": site["name"],
        "summary": "No AI surface mapped for this path.",
        "elements": filter_elements(
            [
                {
                    "action_id": "nav.home",
                    "type": "link",
                    "label": "Home",
                    "href": "/",
                    "scopes": ["view"],
                }
            ]
        ),
    }


def run_action(session: dict[str, Any], action_id: str, args: dict[str, Any]) -> dict[str, Any]:
    cart = cart_by_session.setdefault(session["token"], [])
    token = session["token"]

    if action_id == "nav.home":
        return {"navigated": "/", "page": page_snapshot("/", session)}
    if action_id == "nav.products":
        return {"navigated": "/products", "page": page_snapshot("/products", session)}
    if action_id == "nav.cart":
        return {"navigated": "/cart", "page": page_snapshot("/cart", session)}

    if action_id.startswith("product.view:"):
        pid = action_id.split(":", 1)[1]
        if pid not in PRODUCTS:
            raise KeyError(action_id)
        path = f"/products/{pid}"
        return {"navigated": path, "page": page_snapshot(path, session)}

    if action_id.startswith("product.add:"):
        if "act" not in session["scopes"]:
            raise PermissionError("act")
        pid = action_id.split(":", 1)[1]
        if pid not in PRODUCTS:
            raise KeyError(action_id)
        cart.append(pid)
        return {
            "cart": list(cart),
            "added": PRODUCTS[pid],
            "page": page_snapshot("/cart", session),
        }

    if action_id == "cart.clear":
        if "act" not in session["scopes"]:
            raise PermissionError("act")
        cart_by_session[token] = []
        return {"cart": [], "page": page_snapshot("/cart", session)}

    if action_id == "cart.checkout":
        if "act" not in session["scopes"]:
            raise PermissionError("act")
        items = list(cart)
        cart_by_session[token] = []
        return {
            "checked_out": items,
            "message": "Demo checkout complete. No payment processed.",
            "page": page_snapshot("/cart", session),
        }

    raise KeyError(action_id)


# ---- AI endpoints ----


@app.get("/.well-known/aurif.json")
def well_known():
    site = site_record()
    return jsonify(
        {
            "protocol": PROTOCOL,
            "name": site["name"],
            "site_id": site["id"],
            "handshake": "/ai/handshake",
            "page": "/ai/page",
            "actions": "/ai/actions",
            "audit": "/ai/audit",
            "scopes_supported": list(ALLOWED_SCOPES),
            "agent_welcome": site.get("agent_welcome", ""),
        }
    )


@app.post("/ai/handshake")
def handshake():
    site = site_record()
    data = request.get_json(silent=True) or {}
    agent_id = (data.get("agent_id") or "").strip()
    if not agent_id:
        return jsonify({"ok": False, "error": "agent_id required"}), 400

    requested = data.get("requested_scopes") or ["view"]
    if not isinstance(requested, list):
        return jsonify({"ok": False, "error": "requested_scopes must be a list"}), 400

    provided_key = (
        data.get("site_key")
        or request.headers.get("X-Aurif-Site-Key")
        or ""
    ).strip()
    # Optional key: if provided and wrong, reject. If omitted, allow (demo UX).
    if provided_key and provided_key != site["site_key"]:
        store.log_activity(
            site["id"],
            kind="handshake_denied",
            agent_id=agent_id,
            detail={"reason": "bad_site_key"},
        )
        return jsonify({"ok": False, "error": "invalid site_key"}), 403

    blocked = {a.lower() for a in site.get("blocked_agents", [])}
    if agent_id.lower() in blocked:
        store.log_activity(
            site["id"],
            kind="handshake_denied",
            agent_id=agent_id,
            detail={"reason": "blocked_agent"},
        )
        return jsonify({"ok": False, "error": "agent not allowed by site policy"}), 403

    granted = [s for s in requested if s in ALLOWED_SCOPES]
    if not granted:
        return jsonify({"ok": False, "error": "no supported scopes requested"}), 400

    token = secrets.token_urlsafe(24)
    session = {
        "token": token,
        "agent_id": agent_id,
        "agent_version": str(data.get("agent_version") or "0.0.0"),
        "purpose": str(data.get("purpose") or ""),
        "scopes": granted,
        "site_id": site["id"],
        "created_at": time.time(),
        "expires_at": time.time() + SESSION_TTL,
        "id": str(uuid.uuid4()),
    }
    sessions[token] = session
    cart_by_session[token] = []

    store.log_activity(
        site["id"],
        kind="handshake",
        agent_id=agent_id,
        detail={
            "granted_scopes": granted,
            "purpose": session["purpose"],
            "agent_version": session["agent_version"],
        },
        session_token=token,
    )

    return jsonify(
        {
            "ok": True,
            "session_token": token,
            "granted_scopes": granted,
            "expires_in": SESSION_TTL,
            "site": {"id": site["id"], "name": site["name"]},
            "agent_welcome": site.get("agent_welcome", ""),
            "ai_surface": {"page": "/ai/page", "actions": "/ai/actions"},
        }
    )


@app.get("/ai/page")
def ai_page():
    session, err = require_agent_session("view")
    if err:
        return err
    site = site_record()
    path = request.args.get("path") or "/"
    if not store.endpoint_allowed(site, path=path):
        store.log_activity(
            site["id"],
            kind="page_blocked",
            agent_id=session["agent_id"],
            path=path,
            session_token=session["token"],
        )
        return jsonify(deny_page(path, "Endpoint blocked for AI agents.")), 403

    snap = page_snapshot(path, session)
    store.log_activity(
        site["id"],
        kind="page",
        agent_id=session["agent_id"],
        path=path,
        detail={"blocked": bool(snap.get("blocked"))},
        session_token=session["token"],
    )
    return jsonify(snap)


@app.post("/ai/actions")
def ai_actions():
    session, err = require_agent_session("view")
    if err:
        return err
    site = site_record()
    data = request.get_json(silent=True) or {}
    action_id = (data.get("action_id") or "").strip()
    if not action_id:
        return jsonify({"ok": False, "error": "action_id required"}), 400
    args = data.get("args") or {}
    if not isinstance(args, dict):
        return jsonify({"ok": False, "error": "args must be an object"}), 400

    if not store.endpoint_allowed(site, action_id=action_id):
        store.log_activity(
            site["id"],
            kind="action_blocked",
            agent_id=session["agent_id"],
            action_id=action_id,
            session_token=session["token"],
        )
        return jsonify({"ok": False, "error": "action blocked for AI agents by site owner"}), 403

    needs_act = action_id.startswith("product.add:") or action_id in (
        "cart.clear",
        "cart.checkout",
    )
    if needs_act and "act" not in session["scopes"]:
        return jsonify({"ok": False, "error": "scope 'act' not granted"}), 403

    try:
        result = run_action(session, action_id, args)
    except KeyError:
        return jsonify({"ok": False, "error": "unknown action"}), 404
    except PermissionError:
        return jsonify({"ok": False, "error": "scope 'act' not granted"}), 403

    store.log_activity(
        site["id"],
        kind="action",
        agent_id=session["agent_id"],
        action_id=action_id,
        path=result.get("navigated"),
        detail={"args": args},
        session_token=session["token"],
    )
    page = result.pop("page", None)
    body: dict[str, Any] = {"ok": True, "result": result}
    if page is not None:
        body["page"] = page
    return jsonify(body)


@app.get("/ai/audit")
def ai_audit():
    session = get_agent_session()
    site = site_record()
    events = store.activity_for_site(site["id"], limit=100)
    if session:
        prefix = session["token"][:8] + "…"
        events = [e for e in events if e.get("session") == prefix]
    return jsonify({"ok": True, "events": events})


# ---- Owner dashboard API ----


@app.post("/api/auth/signup")
def api_signup():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip()
    password = data.get("password") or ""
    name = (data.get("name") or "").strip()
    if not email or not password:
        return jsonify({"ok": False, "error": "email and password required"}), 400
    try:
        user = store.create_user(email, password, name)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    token = store.create_owner_session(user["id"])
    resp = jsonify(
        {
            "ok": True,
            "token": token,
            "user": {"id": user["id"], "email": user["email"], "name": user["name"]},
        }
    )
    resp.set_cookie("aurif_owner", token, httponly=True, samesite="Lax", max_age=604800)
    return resp


@app.post("/api/auth/login")
def api_login():
    data = request.get_json(silent=True) or {}
    user = store.authenticate(data.get("email") or "", data.get("password") or "")
    if not user:
        return jsonify({"ok": False, "error": "invalid email or password"}), 401
    token = store.create_owner_session(user["id"])
    resp = jsonify(
        {
            "ok": True,
            "token": token,
            "user": {"id": user["id"], "email": user["email"], "name": user["name"]},
        }
    )
    resp.set_cookie("aurif_owner", token, httponly=True, samesite="Lax", max_age=604800)
    return resp


@app.post("/api/auth/logout")
def api_logout():
    token = request.headers.get("X-Aurif-Owner") or request.cookies.get("aurif_owner")
    store.logout_owner(token)
    resp = jsonify({"ok": True})
    resp.delete_cookie("aurif_owner")
    return resp


@app.get("/api/auth/me")
def api_me():
    session, err = owner_auth()
    if err:
        return err
    user = session["user"]
    return jsonify(
        {
            "ok": True,
            "user": {"id": user["id"], "email": user["email"], "name": user["name"]},
            "sites": store.sites_for_owner(user["id"]),
        }
    )


@app.get("/api/sites")
def api_sites():
    session, err = owner_auth()
    if err:
        return err
    return jsonify({"ok": True, "sites": store.sites_for_owner(session["user"]["id"])})


@app.post("/api/sites")
def api_create_site():
    session, err = owner_auth()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    site = store.create_site(
        session["user"]["id"],
        data.get("name") or "New site",
        data.get("url") or "",
    )
    return jsonify({"ok": True, "site": site})


@app.get("/api/sites/<site_id>")
def api_get_site(site_id: str):
    session, err = owner_auth()
    if err:
        return err
    site = store.get_site(site_id)
    if not site or site["owner_id"] != session["user"]["id"]:
        return jsonify({"ok": False, "error": "not found"}), 404
    return jsonify({"ok": True, "site": store.public_site(site)})


@app.patch("/api/sites/<site_id>")
def api_patch_site(site_id: str):
    session, err = owner_auth()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    try:
        site = store.update_site(site_id, session["user"]["id"], data)
    except PermissionError:
        return jsonify({"ok": False, "error": "not found"}), 404
    return jsonify({"ok": True, "site": site})


@app.put("/api/sites/<site_id>/endpoints/<endpoint_id>")
def api_toggle_endpoint(site_id: str, endpoint_id: str):
    session, err = owner_auth()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    allowed = bool(data.get("agent_access", True))
    try:
        site = store.set_endpoint_access(
            site_id, session["user"]["id"], endpoint_id, allowed
        )
    except PermissionError:
        return jsonify({"ok": False, "error": "not found"}), 404
    return jsonify({"ok": True, "site": site})


@app.get("/api/sites/<site_id>/activity")
def api_activity(site_id: str):
    session, err = owner_auth()
    if err:
        return err
    site = store.get_site(site_id)
    if not site or site["owner_id"] != session["user"]["id"]:
        return jsonify({"ok": False, "error": "not found"}), 404
    return jsonify({"ok": True, "events": store.activity_for_site(site_id, limit=300)})


# ---- Static: demo + dashboard + SDK ----


@app.get("/sdk/<path:filename>")
def sdk_files(filename: str):
    return send_from_directory(SDK_DIR, filename)


@app.get("/styles.css")
def styles():
    return send_from_directory(DEMO_DIR, "styles.css")


@app.get("/dashboard")
@app.get("/dashboard/")
def dashboard_home():
    return send_from_directory(DASH_DIR, "index.html")


@app.get("/dashboard/<path:filename>")
def dashboard_files(filename: str):
    return send_from_directory(DASH_DIR, filename)


@app.get("/")
def home():
    return send_from_directory(DEMO_DIR, "index.html")


@app.get("/products")
def products_page():
    return send_from_directory(DEMO_DIR, "products.html")


@app.get("/products/<pid>")
def product_page(pid: str):
    if pid not in PRODUCTS:
        return send_from_directory(DEMO_DIR, "products.html"), 404
    return send_from_directory(DEMO_DIR, "product.html")


@app.get("/cart")
def cart_page():
    return send_from_directory(DEMO_DIR, "cart.html")


@app.get("/agent-demo")
def agent_demo_redirect():
    """Legacy URL — agent tooling lives on the Aurif product side only."""
    from flask import redirect

    return redirect("/dashboard/agent-console.html", code=302)


@app.get("/api/products")
def api_products():
    return jsonify({"products": list(PRODUCTS.values())})


if __name__ == "__main__":
    site = site_record()
    print(f"Aurif demo     → http://127.0.0.1:8787")
    print(f"Aurif dashboard → http://127.0.0.1:8787/dashboard")
    print(f"Demo login      → owner@aurif.dev / demo1234")
    print(f"Site key        → {site['site_key']}")
    app.run(host="127.0.0.1", port=8787, debug=True)
