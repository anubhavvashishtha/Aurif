#!/usr/bin/env python3
"""
Demo agents against Northline + Aurif.

1) UI scrapers (curl / python-requests) → must be BLOCKED
2) Aurif-protocol agent → sees only allowed fields (price can be redacted)
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

SHOP = "http://127.0.0.1:5173"
API = "http://127.0.0.1:8787"
OWNER = ("owner@aurif.dev", "demo1234")


def req(url: str, method: str = "GET", body: dict | None = None, headers: dict | None = None):
    data = None if body is None else json.dumps(body).encode()
    h = {"Accept": "application/json", **(headers or {})}
    if body is not None:
        h["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(request) as res:
            raw = res.read().decode()
            try:
                parsed = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                parsed = {"_text": raw[:500]}
            return res.status, parsed, dict(res.headers)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"_text": raw[:500]}
        return e.code, parsed, dict(e.headers)


def section(title: str):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def main() -> int:
    failures = 0

    section("1) UI agent via curl UA → Northline storefront")
    status, body, _ = req(SHOP + "/", headers={"User-Agent": "curl/8.4.0"})
    print("status:", status)
    print("snippet:", (body.get("_text") or str(body))[:180].replace("\n", " "))
    if status == 403:
        print("PASS: UI scraper blocked")
    else:
        print("FAIL: expected 403")
        failures += 1

    section("2) UI agent via python-requests → /api/products")
    status, body, _ = req(
        API + "/api/products",
        headers={"User-Agent": "python-requests/2.31.0"},
    )
    print("status:", status)
    print("body:", json.dumps(body, indent=2)[:400])
    if status == 403 and body.get("error") == "anonymous_agent_blocked":
        print("PASS: product API blocked for anonymous agent")
    else:
        print("FAIL: expected anonymous_agent_blocked")
        failures += 1

    section("3) Browser-like UA without human token → /api/products")
    status, body, _ = req(
        API + "/api/products",
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X) Chrome/120.0.0.0 Safari/537.36"
        },
    )
    print("status:", status)
    print("body keys/error:", body.get("error") or list(body.keys())[:5])
    if status in (401, 403) or body.get("error") == "human_captcha_required":
        print("PASS: catalog gated behind human CAPTCHA")
    else:
        print("FAIL: expected human_captcha_required / deny")
        failures += 1

    section("4) Owner login → hide Field Tote price fields")
    status, login, _ = req(
        API + "/api/auth/login",
        method="POST",
        body={"email": OWNER[0], "password": OWNER[1]},
    )
    if status != 200:
        print("FAIL: owner login", login)
        return 1
    token = login["token"]
    owner_h = {"X-Aurif-Owner": token}
    status, patched, _ = req(
        API + "/api/sites/demo-shop/endpoints/page.product.field-tote",
        method="PUT",
        headers=owner_h,
        body={
            "response_fields": [
                {"key": "meta.price", "agent_visible": False},
                {"key": "discount", "agent_visible": False},
            ]
        },
    )
    print("patch status:", status)
    if status != 200:
        print("FAIL: could not patch fields", patched)
        failures += 1
    else:
        print("PASS: redaction policy set (hide meta.price + discount)")

    section("5) Aurif-protocol agent → handshake + /ai/page")
    status, hs, _ = req(
        API + "/ai/handshake",
        method="POST",
        body={
            "agent_id": "policy-check-agent",
            "agent_version": "1.0",
            "requested_scopes": ["view", "act"],
            "purpose": "Read Field Tote details for user",
        },
    )
    print("handshake:", status, "ok=", hs.get("ok"))
    if status != 200 or not hs.get("session_token"):
        print("FAIL: handshake")
        return 1
    session = hs["session_token"]
    status, page, _ = req(
        API + "/ai/page?path=/products/field-tote",
        headers={"X-Aurif-Session": session, "X-Aurif-Protocol": "aurif-1"},
    )
    print("page status:", status)
    print("title:", page.get("title"))
    meta = page.get("meta") or {}
    print("meta keys:", sorted(meta.keys()))
    print("has meta.price:", "price" in meta)
    print("has discount:", "discount" in page)
    if status == 200 and page.get("title") == "Field Tote" and "price" not in meta and "discount" not in page:
        print("PASS: Aurif agent got product, price/discount redacted")
    else:
        print("FAIL: Aurif agent data policy not applied as expected")
        print(json.dumps(page, indent=2)[:800])
        failures += 1

    section("6) Aurif agent blocked action (optional demo)")
    # Turn off add-to-cart action then try
    req(
        API + "/api/sites/demo-shop/endpoints/action.product.add.field-tote",
        method="PUT",
        headers=owner_h,
        body={"agent_access": False},
    )
    status, act, _ = req(
        API + "/ai/actions",
        method="POST",
        headers={"X-Aurif-Session": session, "Content-Type": "application/json"},
        body={"action_id": "product.add:field-tote", "args": {}},
    )
    print("action status:", status, act.get("error"))
    if status == 403:
        print("PASS: denied action blocked for Aurif agent")
    else:
        print("FAIL: expected action 403")
        failures += 1
    # restore action access for later demos
    req(
        API + "/api/sites/demo-shop/endpoints/action.product.add.field-tote",
        method="PUT",
        headers=owner_h,
        body={"agent_access": True},
    )

    section("SUMMARY")
    if failures:
        print(f"{failures} failure(s)")
        return 1
    print("All agent checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
