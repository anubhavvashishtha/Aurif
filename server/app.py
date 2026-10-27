"""
Aurif — AI protocol API + owner dashboard APIs.
Customer storefront UI: Demo-client (Vite). Dashboard UI: Aurif-UI (Vite).
"""

from __future__ import annotations

import secrets
import time
import uuid
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

import store
from agent_gate import blocked_response_body, looks_like_anonymous_agent
from catalog_ai import products_by_slug, public_product
from human_gate import COOKIE_NAME as HUMAN_COOKIE
from human_gate import HUMAN_TTL, human_session_valid, issue_challenge, verify_challenge
from redact import hidden_field_keys, redact_response

ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = ROOT / "demo"
SDK_DIR = ROOT / "sdk"
DASH_DIR = ROOT / "dashboard"

PROTOCOL = "aurif-1"
DEFAULT_SITE_ID = "demo-shop"
SESSION_TTL = 3600
ALLOWED_SCOPES = ("view", "act")

app = Flask(__name__)
CORS(
    app,
    resources={
        r"/*": {
            "origins": [
                "http://127.0.0.1:5173",
                "http://127.0.0.1:5174",
                "http://localhost:5173",
                "http://localhost:5174",
            ]
        }
    },
    supports_credentials=True,
    allow_headers=[
        "Content-Type",
        "X-Aurif-Owner",
        "X-Aurif-Session",
        "X-Aurif-Protocol",
        "X-Aurif-Agent",
        "X-Aurif-Site-Key",
        "X-Aurif-Human",
    ],
)

sessions: dict[str, dict[str, Any]] = {}
cart_by_session: dict[str, list[str]] = {}
PRODUCTS = products_by_slug()


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
            return None, (jsonify({"ok": False, "error": f"scope '{scope}' not granted"}), 403)
    return session, None


def deny_page(path: str, reason: str) -> dict[str, Any]:
    site = site_record()
    return {"path": path, "title": site["name"], "summary": reason, "blocked": True, "elements": []}


def apply_page_redaction(site: dict[str, Any], path: str, snap: dict[str, Any], session: dict[str, Any]) -> dict[str, Any]:
    ep = store.find_endpoint(site, path=path)
    if not ep:
        return snap
    fields = ep.get("response_fields") or []
    hidden = hidden_field_keys(fields)
    out = redact_response(snap, fields)
    if hidden:
        store.log_activity(
            site["id"],
            kind="field_redacted",
            agent_id=session["agent_id"],
            path=path,
            detail={"redacted_fields": hidden},
            session_token=session["token"],
        )
    return out


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
            "summary": welcome or "Gear for slow weekends.",
            "elements": filter_elements(
                [
                    {"action_id": "nav.products", "type": "link", "label": "Shop", "href": "/products", "scopes": ["view"]},
                    {"action_id": "nav.cart", "type": "link", "label": f"Cart ({len(cart)})", "href": "/cart", "scopes": ["view"]},
                    {
                        "action_id": "product.add:field-tote",
                        "type": "button",
                        "label": "Add Field Tote to cart",
                        "scopes": ["act"],
                    },
                ]
            ),
            "meta": {"name": site["name"], "summary": welcome},
            "rating": 4.8,
            "discount": 0,
            "reviews": [],
        }

    if path == "/products":
        elements: list[dict[str, Any]] = [
            {"action_id": "nav.home", "type": "link", "label": "Home", "href": "/", "scopes": ["view"]}
        ]
        for product in PRODUCTS.values():
            pub = public_product(product)
            elements.append(
                {
                    "action_id": f"product.view:{pub['slug']}",
                    "type": "link",
                    "label": f"View {pub['name']}",
                    "href": f"/products/{pub['slug']}",
                    "scopes": ["view"],
                    "meta": {"price": pub["price"], "compare_at": pub["compare_at"], "rating": pub["rating"]},
                }
            )
            elements.append(
                {
                    "action_id": f"product.add:{pub['slug']}",
                    "type": "button",
                    "label": f"Add {pub['name']} to cart",
                    "scopes": ["act"],
                }
            )
        return {
            "path": "/products",
            "title": "Shop — " + site["name"],
            "summary": f"{welcome} {len(PRODUCTS)} products available.".strip(),
            "elements": filter_elements(elements),
            "meta": {"name": "Shop", "summary": f"{len(PRODUCTS)} products"},
            "rating": 4.7,
            "discount": 0,
            "reviews": [],
        }

    if path.startswith("/products/"):
        slug = path.split("/")[-1]
        product = PRODUCTS.get(slug)
        if not product:
            return {
                "path": path,
                "title": "Not found",
                "summary": "Unknown product.",
                "elements": filter_elements(
                    [{"action_id": "nav.products", "type": "link", "label": "Back to shop", "href": "/products", "scopes": ["view"]}]
                ),
            }
        pub = public_product(product)
        return {
            "path": f"/products/{slug}",
            "title": pub["name"],
            "summary": f"{welcome} {pub['summary']}".strip(),
            "elements": filter_elements(
                [
                    {"action_id": "nav.products", "type": "link", "label": "Back to shop", "href": "/products", "scopes": ["view"]},
                    {
                        "action_id": f"product.add:{slug}",
                        "type": "button",
                        "label": f"Add {pub['name']} to cart",
                        "scopes": ["act"],
                    },
                ]
            ),
            "meta": {
                "name": pub["name"],
                "summary": pub["summary"],
                "price": pub["price"],
                "compare_at": pub["compare_at"],
                "rating": pub["rating"],
                "sku": pub["sku"],
                "highlights": pub["highlights"],
            },
            "rating": pub["rating"],
            "discount": pub["discount"],
            "reviews": pub["reviews"],
        }

    if path == "/cart":
        return {
            "path": "/cart",
            "title": "Cart — " + site["name"],
            "summary": f"{welcome} {len(cart)} item(s) in cart.".strip(),
            "elements": filter_elements(
                [
                    {"action_id": "nav.products", "type": "link", "label": "Continue shopping", "href": "/products", "scopes": ["view"]},
                    {"action_id": "cart.clear", "type": "button", "label": "Clear cart", "scopes": ["act"]},
                    {"action_id": "cart.checkout", "type": "button", "label": "Checkout (demo)", "scopes": ["act"]},
                ]
            ),
            "meta": {
                "items": cart,
                "products": [public_product(PRODUCTS[i]) for i in cart if i in PRODUCTS],
            },
            "rating": 0,
            "discount": 0,
            "reviews": [],
        }

    return {
        "path": path,
        "title": site["name"],
        "summary": "No AI surface mapped for this path.",
        "elements": filter_elements(
            [{"action_id": "nav.home", "type": "link", "label": "Home", "href": "/", "scopes": ["view"]}]
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
        slug = action_id.split(":", 1)[1]
        if slug not in PRODUCTS:
            raise KeyError(action_id)
        path = f"/products/{slug}"
        return {"navigated": path, "page": page_snapshot(path, session)}

    if action_id.startswith("product.add:"):
        if "act" not in session["scopes"]:
            raise PermissionError("act")
        slug = action_id.split(":", 1)[1]
        if slug not in PRODUCTS:
            raise KeyError(action_id)
        cart.append(slug)
        return {
            "cart": list(cart),
            "added": public_product(PRODUCTS[slug]),
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

    provided_key = (data.get("site_key") or request.headers.get("X-Aurif-Site-Key") or "").strip()
    if provided_key and provided_key != site["site_key"]:
        store.log_activity(site["id"], kind="handshake_denied", agent_id=agent_id, detail={"reason": "bad_site_key"})
        return jsonify({"ok": False, "error": "invalid site_key"}), 403

    blocked = {a.lower() for a in site.get("blocked_agents", [])}
    if agent_id.lower() in blocked:
        store.log_activity(site["id"], kind="handshake_denied", agent_id=agent_id, detail={"reason": "blocked_agent"})
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
        detail={"granted_scopes": granted, "purpose": session["purpose"]},
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
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    if not store.endpoint_allowed(site, path=path):
        store.log_activity(
            site["id"], kind="page_blocked", agent_id=session["agent_id"], path=path, session_token=session["token"]
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
    snap = apply_page_redaction(site, path, snap, session)
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

    ep = store.find_endpoint(site, action_id=action_id)
    if ep:
        # strip disallowed request fields
        allowed = {f["key"] for f in ep.get("request_fields") or [] if f.get("agent_allowed", True)}
        if allowed:
            args = {k: v for k, v in args.items() if k in allowed or k == "action_id"}

    needs_act = action_id.startswith("product.add:") or action_id in ("cart.clear", "cart.checkout")
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
    if page is not None and isinstance(page, dict) and page.get("path"):
        page = apply_page_redaction(site, page["path"], page, session)
    if ep:
        result = redact_response({"ok": True, "summary": "Action completed.", "result": result}, ep.get("response_fields") or [])
        body = result if isinstance(result, dict) else {"ok": True, "result": result}
    else:
        body = {"ok": True, "result": result}
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
    resp = jsonify({"ok": True, "token": token, "user": {"id": user["id"], "email": user["email"], "name": user["name"]}})
    resp.set_cookie("aurif_owner", token, httponly=True, samesite="Lax", max_age=604800)
    return resp


@app.post("/api/auth/login")
def api_login():
    data = request.get_json(silent=True) or {}
    user = store.authenticate(data.get("email") or "", data.get("password") or "")
    if not user:
        return jsonify({"ok": False, "error": "invalid email or password"}), 401
    token = store.create_owner_session(user["id"])
    resp = jsonify({"ok": True, "token": token, "user": {"id": user["id"], "email": user["email"], "name": user["name"]}})
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
    sites = store.sites_for_owner(user["id"])
    # attach activity onto each site for dashboard hydrate
    enriched = []
    for s in sites:
        enriched.append({**s, "activity": store.activity_for_site(s["id"], limit=300)})
    return jsonify({"ok": True, "user": {"id": user["id"], "email": user["email"], "name": user["name"]}, "sites": enriched})


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
    site = store.create_site(session["user"]["id"], data.get("name") or "New site", data.get("url") or "")
    return jsonify({"ok": True, "site": site})


@app.get("/api/sites/<site_id>")
def api_get_site(site_id: str):
    session, err = owner_auth()
    if err:
        return err
    site = store.get_site(site_id)
    if not site or site["owner_id"] != session["user"]["id"]:
        return jsonify({"ok": False, "error": "not found"}), 404
    pub = store.public_site(site)
    pub["activity"] = store.activity_for_site(site_id, limit=300)
    return jsonify({"ok": True, "site": pub})


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
    try:
        if "response_fields" in data or "request_fields" in data:
            site = store.set_endpoint_fields(
                site_id,
                session["user"]["id"],
                endpoint_id,
                response_fields=data.get("response_fields"),
                request_fields=data.get("request_fields"),
            )
        else:
            site = store.set_endpoint_access(
                site_id, session["user"]["id"], endpoint_id, bool(data.get("agent_access", True))
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


def _reject_anonymous_agent_if_needed():
    """Demo gate: block curl/scrapers/bot UAs unless they hold an Aurif session."""
    site = site_record()
    if not site.get("block_anonymous_agents", True):
        return None
    if request.headers.get("X-Aurif-Session") and get_agent_session():
        return None
    if not looks_like_anonymous_agent(request.headers):
        return None
    store.log_activity(
        site["id"],
        kind="handshake_denied",
        agent_id=request.headers.get("User-Agent", "anonymous")[:80],
        path=request.path,
        detail={"reason": "anonymous_agent_blocked"},
    )
    return jsonify(blocked_response_body(site["name"])), 403


@app.get("/api/public/gate")
def api_public_gate():
    """Customer site asks whether to block anonymous agents (no auth)."""
    site = site_record()
    return jsonify(
        {
            "ok": True,
            "site_id": site["id"],
            "site_name": site["name"],
            "block_anonymous_agents": bool(site.get("block_anonymous_agents", True)),
            "require_human_captcha": bool(site.get("require_human_captcha", True)),
            "well_known": "/.well-known/aurif.json",
            "handshake": "/ai/handshake",
            "ai_page": "/ai/page",
            "ai_actions": "/ai/actions",
            "api_base": "http://127.0.0.1:8787",
        }
    )


@app.get("/api/public/human-challenge")
def api_human_challenge():
    site = site_record()
    if not site.get("require_human_captcha", True):
        return jsonify({"ok": True, "required": False})
    challenge = issue_challenge()
    return jsonify({"ok": True, "required": True, **challenge})


@app.post("/api/public/human-verify")
def api_human_verify():
    site = site_record()
    data = request.get_json(silent=True) or {}
    if not site.get("require_human_captcha", True):
        token = "bypass"
        resp = jsonify({"ok": True, "human_token": token, "expires_in": HUMAN_TTL})
        resp.set_cookie(HUMAN_COOKIE, token, max_age=HUMAN_TTL, httponly=False, samesite="Lax")
        return resp
    token = verify_challenge(str(data.get("challenge_id") or ""), str(data.get("answer") or ""))
    if not token:
        return jsonify({"ok": False, "error": "challenge failed"}), 403
    resp = jsonify({"ok": True, "human_token": token, "expires_in": HUMAN_TTL})
    resp.set_cookie(HUMAN_COOKIE, token, max_age=HUMAN_TTL, httponly=False, samesite="Lax", path="/")
    return resp


@app.get("/api/public/human-check")
def api_human_check():
    token = request.headers.get("X-Aurif-Human") or request.cookies.get(HUMAN_COOKIE)
    site = site_record()
    required = bool(site.get("require_human_captcha", True))
    ok = (not required) or human_session_valid(token) or token == "bypass"
    return jsonify({"ok": ok, "required": required})


@app.get("/api/products")
def api_products():
    blocked = _reject_anonymous_agent_if_needed()
    if blocked:
        return blocked
    site = site_record()
    if site.get("require_human_captcha", True):
        token = request.headers.get("X-Aurif-Human") or request.cookies.get(HUMAN_COOKIE)
        if not human_session_valid(token) and token != "bypass":
            # Browser without CAPTCHA: no catalog JSON
            if not looks_like_anonymous_agent(request.headers):
                return jsonify(
                    {
                        "ok": False,
                        "error": "human_captcha_required",
                        "message": "Complete the human verification on the storefront first.",
                    }
                ), 401
    return jsonify({"products": [public_product(p) for p in PRODUCTS.values()]})


# ---- Legacy static fallbacks (old HTML demos) ----


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
    return jsonify(
        {
            "ok": True,
            "message": "Aurif API server",
            "customer_site": "http://127.0.0.1:5173",
            "dashboard": "http://127.0.0.1:5174",
            "well_known": "/.well-known/aurif.json",
        }
    )


if __name__ == "__main__":
    site = site_record()
    print("Aurif API        → http://127.0.0.1:8787")
    print("Customer site    → http://127.0.0.1:5173  (Demo-client)")
    print("Aurif dashboard  → http://127.0.0.1:5174  (Aurif-UI)")
    print("Demo login       → owner@aurif.dev / demo1234")
    print(f"Site key         → {site['site_key']}")
    app.run(host="127.0.0.1", port=8787, debug=True)
