"""
Aurif — AI protocol API + owner dashboard APIs.
Customer storefront UI: Demo-client (Vite). Dashboard UI: Aurif-UI (Vite).
"""

from __future__ import annotations

import json
import re
import secrets
import time
import uuid
from typing import Any

from flask import Flask, jsonify, request
from flask_cors import CORS

import config
import muse_browse
import muse_client
import store
from agent_gate import blocked_response_body, looks_like_anonymous_agent
from catalog_ai import products_by_slug, public_product
from human_gate import COOKIE_NAME as HUMAN_COOKIE
from human_gate import (
    HUMAN_TTL,
    answer_matches,
    consume_challenge,
    drawing_has_ink,
    human_access_granted,
    issue_challenge,
    issue_human_token,
    peek_challenge,
    register_failed_attempt,
)
from redact import hidden_field_keys, price_link_fields, redact_response

PROTOCOL = "aurif-1"
DEFAULT_SITE_ID = "demo-shop"
SESSION_TTL = 3600
ALLOWED_SCOPES = ("view", "act")

app = Flask(__name__)
CORS(
    app,
    resources={r"/*": {"origins": config.cors_origins()}},
    supports_credentials=True,
    allow_headers=[
        "Content-Type",
        "X-Aurif-Owner",
        "X-Aurif-Session",
        "X-Aurif-Protocol",
        "X-Aurif-Agent",
        "X-Aurif-Site-Key",
        "X-Aurif-Human",
        "X-Demo-As-Agent",
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


def presented_site_key(body: dict | None = None) -> str:
    body = body if isinstance(body, dict) else {}
    return str(
        request.headers.get("X-Aurif-Site-Key")
        or request.args.get("site_key")
        or body.get("site_key")
        or ""
    ).strip()


def reject_without_site_key(
    site: dict[str, Any],
    *,
    kind: str,
    asked: dict[str, Any],
    body: dict | None = None,
    path: str | None = None,
    action_id: str | None = None,
):
    """Every agent data call must present the site key. Agent id is not a block key."""
    key = presented_site_key(body)
    if key and key == site.get("site_key"):
        return None
    reason = "missing_site_key" if not key else "site_key_mismatch"
    store.log_activity(
        site["id"],
        kind=kind,
        agent_id="agent",
        path=path,
        action_id=action_id,
        detail={"accepted": False, "reason": reason, "asked": asked, "navigated": []},
    )
    return (
        jsonify(
            {
                "ok": False,
                "error": "site_key required and must match this site",
                "reason": reason,
                "help": "/ai/help",
            }
        ),
        403,
    )


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


def _agent_label(session: dict[str, Any] | None = None) -> str:
    if session and session.get("agent_id"):
        return str(session["agent_id"])
    return (request.headers.get("X-Aurif-Agent") or "agent").strip() or "agent"


def log_denial(
    site: dict[str, Any],
    *,
    kind: str,
    reason: str,
    path: str | None = None,
    action_id: str | None = None,
    asked: dict[str, Any] | None = None,
    session: dict[str, Any] | None = None,
) -> None:
    store.log_activity(
        site["id"],
        kind=kind,
        agent_id=_agent_label(session),
        path=path,
        action_id=action_id,
        session_token=(session or {}).get("token"),
        detail={"accepted": False, "reason": reason, "asked": asked or {}, "navigated": []},
    )


def _session_denial_reason(err: tuple[Any, int]) -> str:
    status = err[1] if len(err) > 1 else 401
    return "no_session" if status == 401 else "scope_not_granted"


def apply_page_redaction(site: dict[str, Any], path: str, snap: dict[str, Any], session: dict[str, Any]) -> dict[str, Any]:
    path = store.canonical_ai_path(path)
    ep = store.find_endpoint(site, path=path)
    if not ep:
        return snap
    fields = ep.get("response_fields") or []
    # Price hidden on any page is withheld on every page the agent reads.
    # The shop list stores it as meta.products[].price and elements[].meta.price,
    # which are different paths from the detail page's meta.price.
    linked = price_link_fields(site.get("endpoints") or [])
    hidden = hidden_field_keys(fields)
    out = redact_response(snap, fields, linked)
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
    path, decision = store.page_decision(site, path)
    if decision == "unmapped":
        return deny_page(path, "No AI surface mapped for this path.")
    if decision != "allow":
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

    ep = store.find_endpoint(site, path=path) or {}
    endpoint_id = str(ep.get("id") or "")

    if endpoint_id == "page.home":
        return {
            "path": path,
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
        }

    if endpoint_id == "page.products":
        elements: list[dict[str, Any]] = [
            {"action_id": "nav.home", "type": "link", "label": "Home", "href": "/", "scopes": ["view"]}
        ]
        catalog: list[dict[str, Any]] = []
        for product in PRODUCTS.values():
            pub = public_product(product)
            catalog.append(
                {
                    "name": pub["name"],
                    "slug": pub["slug"],
                    "price": pub["price"],
                    "rating": pub["rating"],
                    "href": f"/products/{pub['slug']}",
                }
            )
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
            "path": path,
            "title": "Shop — " + site["name"],
            "summary": f"{welcome} {len(PRODUCTS)} products available.".strip(),
            "elements": filter_elements(elements),
            "meta": {"products": catalog},
        }

    if endpoint_id == "page.product":
        slug = store.capture_wildcard(str(ep.get("path") or ""), path) or ""
        product = PRODUCTS.get(slug) if slug else None
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
            "path": path,
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

    if endpoint_id == "page.cart":
        return {
            "path": path,
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
                "products": [
                    {"name": p["name"], "price": p["price"]}
                    for i in cart
                    if i in PRODUCTS
                    for p in [public_product(PRODUCTS[i])]
                ],
            },
        }

    sample = ep.get("sample_response") if isinstance(ep.get("sample_response"), dict) else {}
    elements = sample.get("elements") if isinstance(sample.get("elements"), list) else []
    meta = sample.get("meta") if isinstance(sample.get("meta"), dict) else {}
    return {
        "path": path,
        "title": sample.get("title") or ep.get("label") or site["name"],
        "summary": sample.get("summary") or welcome,
        "elements": filter_elements([item for item in elements if isinstance(item, dict)]),
        "meta": dict(meta),
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
        pub = public_product(PRODUCTS[slug])
        return {
            "cart": list(cart),
            "added": {
                "slug": pub["slug"],
                "name": pub["name"],
                "summary": pub.get("summary"),
                "price": pub.get("price"),
                "compare_at": pub.get("compare_at"),
                "discount": pub.get("discount"),
                "rating": pub.get("rating"),
                "sku": pub.get("sku"),
            },
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
            "help": "/ai/help",
            "handshake": "/ai/handshake",
            "page": "/ai/page",
            "actions": "/ai/actions",
            "audit": "/ai/audit",
            "auth": {
                "open": ["/ai/help", "/.well-known/aurif.json"],
                "site_key_header": "X-Aurif-Site-Key",
                "site_key_field": "site_key",
                "note": "Every other agent call must send the site key. Requests without a matching key are refused. Agents are not blocked by id.",
            },
            "scopes_supported": list(ALLOWED_SCOPES),
            "agent_welcome": site.get("agent_welcome", ""),
        }
    )


@app.get("/ai/help")
def ai_help():
    """Open to every agent. Describes what later calls must send. No site key."""
    site = site_record()
    return jsonify(
        {
            "ok": True,
            "protocol": PROTOCOL,
            "open": True,
            "site": {"id": site["id"], "name": site["name"]},
            "auth": {
                "header": "X-Aurif-Site-Key",
                "body_field": "site_key",
                "required_on": ["/ai/handshake", "/ai/page", "/ai/actions", "/ai/audit"],
                "note": "Send the site key on every call except this one and /.well-known/aurif.json. A missing or wrong key is refused. Aurif does not block by agent id.",
            },
            "endpoints": [
                {
                    "method": "GET",
                    "path": "/ai/help",
                    "site_key": False,
                    "send": {},
                    "returns": "This document.",
                },
                {
                    "method": "POST",
                    "path": "/ai/handshake",
                    "site_key": True,
                    "send": {
                        "site_key": "required string, must match the site",
                        "purpose": "why you are visiting",
                        "requested_scopes": ["view"],
                    },
                    "returns": "session_token and granted_scopes",
                },
                {
                    "method": "GET",
                    "path": "/ai/page",
                    "site_key": True,
                    "send": {
                        "headers": {"X-Aurif-Site-Key": "required", "X-Aurif-Session": "session_token from handshake"},
                        "query": {"path": "page path, for example / or /products"},
                    },
                    "returns": "JSON for that page. Hidden fields are omitted. A closed endpoint is 403.",
                },
                {
                    "method": "POST",
                    "path": "/ai/actions",
                    "site_key": True,
                    "send": {
                        "headers": {"X-Aurif-Site-Key": "required", "X-Aurif-Session": "session_token from handshake"},
                        "body": {"action_id": "id from the page elements", "args": {}},
                    },
                    "returns": "Action result, or 403 if that action is closed or act was not granted.",
                },
            ],
        }
    )


@app.post("/ai/handshake")
def handshake():
    site = site_record()
    data = request.get_json(silent=True) or {}
    agent_id = (data.get("agent_id") or "agent").strip() or "agent"
    asked = {
        "method": "POST",
        "path": "/ai/handshake",
        "purpose": str(data.get("purpose") or ""),
        "requested_scopes": data.get("requested_scopes") or ["view"],
    }
    denied = reject_without_site_key(site, kind="handshake_denied", asked=asked, body=data)
    if denied:
        return denied

    requested = data.get("requested_scopes") or ["view"]
    if not isinstance(requested, list):
        return jsonify({"ok": False, "error": "requested_scopes must be a list"}), 400

    granted = [s for s in requested if s in ALLOWED_SCOPES]
    if not granted:
        return jsonify({"ok": False, "error": "no supported scopes requested"}), 400

    purpose = str(data.get("purpose") or "")
    risk = muse_client.score_purpose(purpose)
    if risk.get("drop_act") and "act" in granted:
        granted = [s for s in granted if s != "act"]
    if not granted:
        granted = ["view"]

    token = secrets.token_urlsafe(24)
    session = {
        "token": token,
        "agent_id": agent_id,
        "agent_version": str(data.get("agent_version") or "0.0.0"),
        "purpose": purpose,
        "scopes": granted,
        "site_id": site["id"],
        "created_at": time.time(),
        "expires_at": time.time() + SESSION_TTL,
        "id": str(uuid.uuid4()),
        "purpose_risk": risk,
    }
    sessions[token] = session
    cart_by_session[token] = []
    store.log_activity(
        site["id"],
        kind="handshake",
        agent_id=agent_id,
        detail={
            "accepted": True,
            "reason": "site_key matched",
            "asked": asked,
            "navigated": [],
            "granted_scopes": granted,
            "purpose": purpose,
            "purpose_risk": risk,
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
            "purpose_risk": risk,
        }
    )


@app.get("/ai/page")
def ai_page():
    site = site_record()
    raw_path = request.args.get("path") if request.args.get("path") is not None else "/"
    path = store.canonical_ai_path(raw_path)
    asked = {"method": "GET", "path": "/ai/page", "query": {"path": raw_path}}
    denied = reject_without_site_key(site, kind="page_blocked", asked=asked, path=path)
    if denied:
        return denied
    session, err = require_agent_session("view")
    if err:
        log_denial(
            site,
            kind="page_blocked",
            reason=_session_denial_reason(err),
            path=path,
            asked=asked,
        )
        return err
    path, decision = store.page_decision(site, path)
    if decision != "allow":
        reason = "unmapped_path" if decision == "unmapped" else "endpoint closed"
        message = (
            "No AI surface mapped for this path."
            if decision == "unmapped"
            else "Endpoint blocked for AI agents."
        )
        log_denial(
            site,
            kind="page_blocked",
            reason=reason,
            path=path,
            asked=asked,
            session=session,
        )
        return jsonify(deny_page(path, message)), 403

    snap = page_snapshot(path, session)
    if snap.get("blocked"):
        log_denial(
            site,
            kind="page_blocked",
            reason="endpoint closed",
            path=path,
            asked=asked,
            session=session,
        )
        return jsonify(snap), 403
    store.log_activity(
        site["id"],
        kind="page",
        agent_id=session["agent_id"],
        path=path,
        detail={
            "accepted": True,
            "reason": "site_key matched",
            "asked": asked,
            "navigated": [path],
            "blocked": bool(snap.get("blocked")),
        },
        session_token=session["token"],
    )
    snap = apply_page_redaction(site, path, snap, session)
    return jsonify(snap)


@app.post("/ai/actions")
def ai_actions():
    site = site_record()
    data = request.get_json(silent=True) or {}
    action_id = (data.get("action_id") or "").strip()
    asked = {"method": "POST", "path": "/ai/actions", "action_id": action_id, "args": data.get("args") or {}}
    denied = reject_without_site_key(site, kind="action_blocked", asked=asked, body=data, action_id=action_id or None)
    if denied:
        return denied
    session, err = require_agent_session("view")
    if err:
        log_denial(
            site,
            kind="action_blocked",
            reason=_session_denial_reason(err),
            action_id=action_id or None,
            asked=asked,
        )
        return err
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
            detail={"accepted": False, "reason": "endpoint closed", "asked": asked, "navigated": []},
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
        log_denial(
            site,
            kind="action_blocked",
            reason="scope_not_granted",
            action_id=action_id,
            asked=asked,
            session=session,
        )
        return jsonify({"ok": False, "error": "scope 'act' not granted"}), 403

    before_cart = list(cart_by_session.get(session["token"], []))
    try:
        result = run_action(session, action_id, args)
    except KeyError:
        log_denial(
            site,
            kind="action_blocked",
            reason="unknown_action",
            action_id=action_id,
            asked=asked,
            session=session,
        )
        return jsonify({"ok": False, "error": "unknown action"}), 404
    except PermissionError:
        log_denial(
            site,
            kind="action_blocked",
            reason="scope_not_granted",
            action_id=action_id,
            asked=asked,
            session=session,
        )
        return jsonify({"ok": False, "error": "scope 'act' not granted"}), 403

    page = result.get("page") if isinstance(result, dict) else None
    if isinstance(page, dict) and page.get("blocked"):
        cart_by_session[session["token"]] = before_cart
        target = str(page.get("path") or "")
        _, page_state = store.page_decision(site, target)
        log_denial(
            site,
            kind="page_blocked",
            reason="unmapped_path" if page_state == "unmapped" else "endpoint closed",
            path=target or None,
            action_id=action_id,
            asked=asked,
            session=session,
        )
        return jsonify({"ok": False, "error": "Endpoint blocked for AI agents.", "page": page}), 403

    store.log_activity(
        site["id"],
        kind="action",
        agent_id=session["agent_id"],
        action_id=action_id,
        path=result.get("navigated"),
        detail={
            "accepted": True,
            "reason": "site_key matched",
            "asked": asked,
            "navigated": [result.get("navigated")] if result.get("navigated") else [],
            "args": args,
        },
        session_token=session["token"],
    )
    page = result.pop("page", None)
    if page is not None and isinstance(page, dict) and page.get("path"):
        page = apply_page_redaction(site, page["path"], page, session)
    action_fields = (ep or {}).get("response_fields") or []
    linked = price_link_fields(site.get("endpoints") or [])
    body = redact_response(
        {"ok": True, "summary": "Action completed.", "result": result},
        action_fields,
        linked,
    )
    if not isinstance(body, dict):
        body = {"ok": True, "result": body}
    if page is not None:
        body["page"] = page
        if linked:
            body = redact_response(body, [], linked)
    return jsonify(body)


@app.get("/ai/audit")
def ai_audit():
    site = site_record()
    denied = reject_without_site_key(
        site,
        kind="page_blocked",
        asked={"method": "GET", "path": "/ai/audit"},
        path="/ai/audit",
    )
    if denied:
        return denied
    session, err = require_agent_session("view")
    if err:
        log_denial(
            site,
            kind="page_blocked",
            reason=_session_denial_reason(err),
            path="/ai/audit",
            asked={"method": "GET", "path": "/ai/audit"},
        )
        return err
    events = store.activity_for_site(site["id"], limit=100)
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


def _owner_site(site_id: str, session: dict[str, Any]):
    site = store.get_site(site_id)
    if not site or site["owner_id"] != session["user"]["id"]:
        return None, (jsonify({"ok": False, "error": "not found"}), 404)
    return site, None


def _ai_feature_body(feature: str, result: dict[str, Any]):
    """Owner AI response. `model` stays a string; `model_info` is the safe card."""
    card = result.get("model") if isinstance(result.get("model"), dict) else muse_client.model_card()
    body: dict[str, Any] = {
        "ok": True,
        feature: result,
        "model": card.get("id") or muse_client.text_model_id(),
        "model_info": {
            "id": card.get("id") or "",
            "provider": card.get("provider") or "",
            "label": card.get("label") or "",
        },
        "latency_ms": result.get("latency_ms"),
        "source": result.get("source") or "model",
        "degraded": bool(result.get("degraded")),
        "fallback": result.get("fallback"),
    }
    if result.get("warning"):
        body["warning"] = result["warning"]
    return body


@app.post("/api/sites/<site_id>/ai/policy-propose")
def api_policy_propose(site_id: str):
    session, err = owner_auth()
    if err:
        return err
    site, err = _owner_site(site_id, session)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    instruction = (data.get("instruction") or "").strip()
    if not instruction:
        return jsonify({"ok": False, "error": "instruction required"}), 400
    # propose_policy catches model errors and returns a keyword draft. It does not write policy.
    proposal = muse_client.propose_policy(instruction, site.get("endpoints") or [])
    return jsonify(_ai_feature_body("proposal", proposal))


@app.post("/api/sites/<site_id>/ai/policy-apply")
def api_policy_apply(site_id: str):
    """Apply owner-confirmed Muse policy patches via existing store mutators."""
    session, err = owner_auth()
    if err:
        return err
    site, err = _owner_site(site_id, session)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    patches = data.get("patches") or []
    if not isinstance(patches, list):
        return jsonify({"ok": False, "error": "patches must be a list"}), 400
    uid = session["user"]["id"]
    try:
        for patch in patches:
            if not isinstance(patch, dict):
                continue
            eid = (patch.get("endpoint_id") or "").strip()
            if not eid:
                continue
            if "agent_access" in patch:
                site = store.set_endpoint_access(site_id, uid, eid, bool(patch["agent_access"]))
            if "response_fields" in patch or "request_fields" in patch:
                site = store.set_endpoint_fields(
                    site_id,
                    uid,
                    eid,
                    response_fields=patch.get("response_fields"),
                    request_fields=patch.get("request_fields"),
                )
        add_blocked = data.get("blocked_agents_add") or []
        if isinstance(add_blocked, list) and add_blocked:
            current = list(site.get("blocked_agents") or [])
            for a in add_blocked:
                a = str(a).strip()
                if a and a not in current:
                    current.append(a)
            site = store.update_site(site_id, uid, {"blocked_agents": current})
    except PermissionError:
        return jsonify({"ok": False, "error": "not found"}), 404
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True, "site": store.public_site(site)})


@app.post("/api/sites/<site_id>/ai/activity-summary")
def api_activity_summary(site_id: str):
    session, err = owner_auth()
    if err:
        return err
    site, err = _owner_site(site_id, session)
    if err:
        return err
    events = store.activity_for_site(site_id, limit=80)
    # summarize_activity keeps the counted brief when the model call fails.
    summary = muse_client.summarize_activity(events)
    return jsonify(_ai_feature_body("summary", summary))


def _path_from_message(message: str) -> str:
    return muse_browse.shop_path_from_message(message, PRODUCTS)


def _fmt_money(value: Any) -> str | None:
    if value is None or value == "":
        return None
    try:
        return f"${float(value):g}"
    except (TypeError, ValueError):
        return str(value)


def _fmt_field_value(key: str, value: Any) -> str | None:
    if value is None or value == "" or value == [] or value == {}:
        return None
    key_l = key.lower()
    if key_l in ("price", "compare_at", "compareat") or key_l.endswith("_price"):
        money = _fmt_money(value)
        return money
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        if all(isinstance(x, (str, int, float)) for x in value):
            return ", ".join(str(x) for x in value)
        parts = []
        for item in value[:8]:
            if isinstance(item, dict):
                label = (
                    item.get("name")
                    or item.get("title")
                    or item.get("label")
                    or item.get("author")
                    or item.get("slug")
                )
                extra = []
                if item.get("price") is not None:
                    money = _fmt_money(item.get("price"))
                    if money:
                        extra.append(money)
                if item.get("rating") is not None:
                    extra.append(f"rating {item.get('rating')}")
                if label:
                    parts.append(f"{label}" + (f" ({', '.join(extra)})" if extra else ""))
                else:
                    parts.append(json.dumps(item, ensure_ascii=True))
            else:
                parts.append(str(item))
        return "; ".join(parts) if parts else None
    if isinstance(value, dict):
        bits = []
        for k, v in value.items():
            rendered = _fmt_field_value(str(k), v)
            if rendered:
                bits.append(f"{str(k).replace('_', ' ')}: {rendered}")
        return "; ".join(bits) if bits else None
    return str(value)


def _collect_visible_fields(page: dict[str, Any]) -> list[tuple[str, str]]:
    """Turn the page JSON Muse received into plain label/value pairs."""
    fields: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(label: str, value: Any) -> None:
        key = label.lower()
        if key in seen:
            return
        rendered = _fmt_field_value(label, value)
        if not rendered:
            return
        seen.add(key)
        fields.append((label.replace("_", " ").capitalize(), rendered))

    add("title", page.get("title"))
    add("summary", page.get("summary"))
    meta = page.get("meta") if isinstance(page.get("meta"), dict) else {}
    preferred = (
        "name",
        "summary",
        "price",
        "compare_at",
        "rating",
        "discount",
        "sku",
        "category",
        "tagline",
        "highlights",
        "stock",
        "review_count",
        "items",
        "products",
    )
    for key in preferred:
        if key in meta:
            add(key, meta.get(key))
    for key, value in meta.items():
        if key in preferred or key in ("description",):
            continue
        add(str(key), value)
    for key in ("rating", "discount", "reviews"):
        if key in page:
            add(key, page.get(key))
    return fields


def _describe_page_for_owner(page: dict[str, Any]) -> str:
    """Deterministic plain-English report of what Muse could see."""
    if page.get("blocked"):
        reason = page.get("summary") or page.get("error") or "This page is blocked for agents."
        return f"The site did not show me page details. It said: {reason}"

    fields = _collect_visible_fields(page)
    product_rows: list[str] = []
    for el in page.get("elements") or []:
        if not isinstance(el, dict):
            continue
        meta = el.get("meta") if isinstance(el.get("meta"), dict) else {}
        label = str(el.get("label") or "")
        if not label.lower().startswith("view ") or not meta:
            continue
        name = label[5:].strip()
        bits = [name]
        if meta.get("price") is not None:
            money = _fmt_money(meta.get("price"))
            if money:
                bits.append(f"price {money}")
        if meta.get("rating") is not None:
            bits.append(f"rating {meta.get('rating')}")
        product_rows.append(" — ".join(bits))

    actions = [
        str(el.get("label"))
        for el in (page.get("elements") or [])
        if isinstance(el, dict) and el.get("label") and not str(el.get("label")).lower().startswith("view ")
    ]

    lines: list[str] = ["Here's what the site showed me:"]
    if fields:
        for label, value in fields:
            lines.append(f"- {label}: {value}")
    if product_rows:
        lines.append("- Products:")
        for row in product_rows:
            lines.append(f"  • {row}")
    if actions:
        lines.append("- Available actions: " + ", ".join(actions))
    if len(lines) == 1:
        lines.append("- No visible fields were returned for this page.")
    return "\n".join(lines)


def _describe_denied_for_owner(body: dict[str, Any]) -> str:
    error = body.get("error") or body.get("summary") or body.get("reason")
    reason = body.get("reason")
    if error and reason and reason != error:
        detail = f"{error} ({str(reason).replace('_', ' ')})"
    elif error:
        detail = str(error)
    else:
        detail = json.dumps(body, ensure_ascii=True)
    return f"The site did not share page data with me. Its response was: {detail}."


def _muse_report_site_response(fallback: str, *, seen_fields: list[tuple[str, str]] | None = None) -> str:
    """Ask Muse to explain what it saw; keep the deterministic fallback if polish fails."""
    field_block = ""
    if seen_fields:
        field_block = "Visible fields Muse received:\n" + "\n".join(f"- {k}: {v}" for k, v in seen_fields)
    prompt = (
        "You are Muse inside Aurif, talking to the site owner.\n"
        "Explain what you could see on the website in plain English.\n"
        "Rules:\n"
        "- Do NOT mention HTTP status, path, JSON, endpoints, or protocol jargon.\n"
        "- Describe the fields you received: name, title, price, rating, and so on.\n"
        "- Write a short natural answer, like: I can see this product. Its name is …, price is …\n"
        "- If nothing was shared, say the site did not show you page details and quote what it said.\n"
        "- Use only the facts below.\n\n"
        f"{field_block}\n\nFallback draft:\n{fallback}"
    )
    try:
        polished = muse_client.complete(
            [{"role": "user", "content": prompt}],
            max_tokens=320,
            temperature=0.25,
        )
        cleaned = polished.strip()
        words = cleaned.split()
        bad = any(token in cleaned.lower() for token in ("http ", "path ", "json", "status code"))
        if cleaned and 8 < len(words) < 180 and not bad:
            return cleaned
    except Exception:
        pass
    return fallback


@app.get("/api/ai/models")
def api_ai_models():
    """Models available in the Agent dashboard dropdown."""
    owner, err = owner_auth()
    if err:
        return err
    _ = owner
    try:
        models = muse_client.list_agent_models()
    except RuntimeError as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    current = next((m for m in models if m.get("default")), models[0] if models else None)
    return jsonify(
        {
            "ok": True,
            "models": models,
            "current": current,
            "providers": muse_client.api_providers(),
            "health": muse_client.health_snapshot(),
        }
    )


@app.post("/api/ai/agent-chat")
def api_agent_chat():
    """Owner chat: Muse browses the real storefront like a normal agent (no /ai/* protocol)."""
    owner, err = owner_auth()
    if err:
        return err
    _ = owner
    data = request.get_json(silent=True) or {}
    message = str(data.get("message") or "").strip()
    if not message:
        return jsonify({"ok": False, "error": "message required"}), 400

    site = site_record()
    path = muse_browse.shop_path_from_message(message, PRODUCTS)
    # Owner toggle: only attach site key when explicitly enabled in the Agent dashboard.
    use_site_key = bool(data.get("use_site_key"))
    site_key = str(data.get("site_key") or "").strip() if use_site_key else ""
    try:
        model_info = muse_client.resolve_model(str(data.get("model") or "").strip() or None)
    except RuntimeError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    result = muse_browse.browse_as_agent(
        site=site,
        path=path,
        products=PRODUCTS,
        message=message,
        site_key=site_key or None,
        model=model_info["id"],
        provider=model_info["provider"],
    )

    kind = "page_blocked" if result.get("denied") else "page"
    store.log_activity(
        site["id"],
        kind=kind,
        agent_id="muse-dashboard/1.0",
        path=path,
        detail={
            "accepted": not bool(result.get("denied")),
            "reason": "muse_storefront_browse",
            "asked": {"method": "GET", "url": result.get("url"), "purpose": message[:240]},
            "navigated": [path],
            "captcha": result.get("captcha"),
            "storefront_status": result.get("status"),
            "site_key_used": bool(site_key),
            "model": model_info,
        },
    )

    return jsonify(
        {
            "ok": True,
            "denied": bool(result.get("denied")),
            "reply": result.get("reply"),
            "steps": result.get("steps") or [],
            "path": path,
            "status": result.get("status"),
            "fields": result.get("fields") or [],
            "site_response": result.get("site_response"),
            "captcha": result.get("captcha"),
            "url": result.get("url"),
            "model": model_info,
        }
    )


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
            "api_base": config.api_public_url(),
            "health": "/api/health",
            "model_degraded": bool(muse_client.health_snapshot()["degraded"]),
        }
    )


@app.get("/api/health")
def api_health():
    """Model configuration and the last text/vision call. No API keys."""
    snap = muse_client.health_snapshot()
    return jsonify(snap), (200 if snap["ok"] else 503)


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
        token = issue_human_token()
        resp = jsonify({"ok": True, "human_token": token, "expires_in": HUMAN_TTL})
        resp.set_cookie(HUMAN_COOKIE, token, max_age=HUMAN_TTL, httponly=False, samesite="Lax")
        return resp

    challenge_id = str(data.get("challenge_id") or "").strip()
    image = str(data.get("image") or data.get("drawing") or "").strip()
    answer = str(data.get("answer") or "").strip()
    row = peek_challenge(challenge_id)
    if not row:
        return jsonify({"ok": False, "error": "challenge expired — refresh and try again"}), 403
    target = str(row.get("target") or "")
    if not image.startswith("data:image/") and not answer:
        return jsonify({"ok": False, "error": "drawing image required"}), 400

    verdict: dict[str, Any] | None = None
    if image.startswith("data:image/"):
        try:
            verdict = muse_client.verify_drawing(image, target)
        except Exception as e:
            muse_client.note_model_failure("vision", e)
            verdict = {"ok": False, "unavailable": True, "reason": str(e)}

    if verdict and verdict.get("ok") and not verdict.get("unavailable"):
        consume_challenge(challenge_id)
        token = issue_human_token()
        resp = jsonify(
            {
                "ok": True,
                "human_token": token,
                "expires_in": HUMAN_TTL,
                "degraded": False,
                "method": "vision",
                "verdict": {
                    "read_as": verdict.get("read_as"),
                    "model": verdict.get("model"),
                },
            }
        )
        resp.set_cookie(HUMAN_COOKIE, token, max_age=HUMAN_TTL, httponly=False, samesite="Lax", path="/")
        return resp

    vision_down = bool(verdict and verdict.get("unavailable")) or (
        verdict is None and not muse_client.vision_configured()
    )
    if vision_down:
        method = ""
        if answer_matches(target, answer):
            method = "typed_fallback"
        elif image.startswith("data:image/") and drawing_has_ink(image):
            method = "ink_fallback"
        if method:
            muse_client.log.warning(
                "CAPTCHA vision unavailable; accepted %s for the human storefront only (no agent act)",
                method,
            )
            consume_challenge(challenge_id)
            token = issue_human_token()
            warning = (
                "Vision model unavailable. This check opens the human storefront only "
                "and does not grant agent act."
            )
            resp = jsonify(
                {
                    "ok": True,
                    "degraded": True,
                    "method": method,
                    "warning": warning,
                    "human_token": token,
                    "expires_in": HUMAN_TTL,
                    "model_status": muse_client.health_snapshot()["vision"],
                }
            )
            resp.set_cookie(
                HUMAN_COOKIE, token, max_age=HUMAN_TTL, httponly=False, samesite="Lax", path="/"
            )
            return resp
        return jsonify(
            {
                "ok": False,
                "degraded": True,
                "error": (
                    "Vision model unavailable. Draw on the pad and submit again, or send "
                    "answer set to the characters in the prompt. This does not grant agent act."
                ),
                "fallback": {
                    "challenge_id": challenge_id,
                    "type": "type",
                    "target": target,
                    "prompt": f'Type these characters to continue: {target}',
                },
                "model_status": muse_client.health_snapshot()["vision"],
            }
        ), 403

    if not verdict or not verdict.get("ok"):
        if verdict is None:
            return jsonify({"ok": False, "error": "drawing image required"}), 400
        # A vision-provider result that is not marked unavailable stays a hard
        # failure and does not spend a drawing attempt. Real outages set
        # unavailable and already took the storefront-only fallback above.
        reason = str(verdict.get("reason") or "")
        if reason.startswith("vision provider") and not verdict.get("unavailable"):
            return jsonify(
                {
                    "ok": False,
                    "error": reason,
                    "model": verdict.get("model"),
                    "provider": verdict.get("provider"),
                }
            ), 502
        # One redraw, then the challenge is consumed. Wrong drawings are sent to the API path.
        state = register_failed_attempt(challenge_id)
        error = verdict.get("reason") or "drawing did not match"
        if state == "exhausted":
            error = "too many attempts — refresh and try again"
        return jsonify(
            {
                "ok": False,
                "error": error,
                "agent_access": {
                    "title": "Use the API with a site key",
                    "message": (
                        "In order to access this page as an agent, send a request to the Aurif API "
                        "with the required site key. The human storefront stays closed."
                    ),
                    "steps": [
                        {"method": "GET", "path": "/ai/help", "note": "Open help — no site key"},
                        {
                            "method": "POST",
                            "path": "/ai/handshake",
                            "note": "Body must include site_key (or header X-Aurif-Site-Key)",
                        },
                        {
                            "method": "GET",
                            "path": "/ai/page?path=/",
                            "note": "Send X-Aurif-Site-Key and X-Aurif-Session from handshake",
                        },
                    ],
                    "api_base": config.api_public_url(),
                    "site_key_header": "X-Aurif-Site-Key",
                },
                "verdict": {
                    "read_as": verdict.get("read_as"),
                    "match": verdict.get("match"),
                    "human_like": verdict.get("human_like"),
                    "model": verdict.get("model"),
                },
            }
        ), 403

    return jsonify({"ok": False, "error": "drawing did not match"}), 403


@app.get("/api/public/human-check")
def api_human_check():
    token = request.headers.get("X-Aurif-Human") or request.cookies.get(HUMAN_COOKIE)
    site = site_record()
    required = bool(site.get("require_human_captcha", True))
    ok = human_access_granted(token, required=required)
    return jsonify({"ok": ok, "required": required})


@app.get("/api/products")
def api_products():
    blocked = _reject_anonymous_agent_if_needed()
    if blocked:
        return blocked
    site = site_record()
    if site.get("require_human_captcha", True):
        token = request.headers.get("X-Aurif-Human") or request.cookies.get(HUMAN_COOKIE)
        if not human_access_granted(token, required=True):
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


@app.get("/")
def home():
    return jsonify(
        {
            "ok": True,
            "message": "Aurif API server",
            "customer_site": config.customer_site_url(),
            "dashboard": config.dashboard_url(),
            "well_known": "/.well-known/aurif.json",
        }
    )


if __name__ == "__main__":
    site = site_record()
    debug = config.flask_debug()
    print(f"Aurif API        → {config.api_public_url()}")
    print(f"Customer site    → {config.customer_site_url()}  (Demo-client)")
    print(f"Aurif dashboard  → {config.dashboard_url()}  (Aurif-UI)")
    print("Demo login       → owner@aurif.dev / demo1234")
    print(f"Site key         → {site['site_key']}")
    muse_client.log_active_models(echo=True)
    app.run(host=config.bind_host(), port=config.port(), debug=debug, use_reloader=debug)
