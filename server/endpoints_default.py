"""Default AI endpoints + response/request field schemas for Northline demo."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def _rf(key: str, typ: str, visible: bool = True) -> dict[str, Any]:
    label = key.split(".")[-1].replace("[]", "")
    return {"key": key, "label": label, "type": typ, "agent_visible": visible}


def _page(
    eid: str,
    label: str,
    path: str,
    sample: dict[str, Any],
    field_keys: list[tuple[str, str]],
    *,
    access: bool = True,
    hide: set[str] | None = None,
) -> dict[str, Any]:
    hide = hide or set()
    return {
        "id": eid,
        "label": label,
        "kind": "page",
        "path": path,
        "ref": path,
        "agent_access": access,
        "direction": "read",
        "response_fields": [
            _rf(k, t, visible=(k not in hide)) for k, t in field_keys
        ],
        "request_fields": [],
        "sample_response": sample,
        "sample_request": {},
    }


def _action(
    eid: str,
    label: str,
    action_id: str,
    *,
    access: bool = True,
) -> dict[str, Any]:
    return {
        "id": eid,
        "label": label,
        "kind": "action",
        "action_id": action_id,
        "ref": action_id,
        "agent_access": access,
        "direction": "both",
        "response_fields": [
            _rf("ok", "boolean"),
            _rf("summary", "string"),
            _rf("result", "object"),
        ],
        "request_fields": [
            {"key": "quantity", "label": "Quantity", "agent_allowed": True},
            {"key": "args", "label": "Action arguments", "agent_allowed": True},
            {"key": "email", "label": "Email address", "agent_allowed": False},
        ],
        "sample_response": {"ok": True, "summary": "Action completed.", "result": {}},
        "sample_request": {
            "quantity": 1,
            "args": {"product_id": "field-tote"},
            "email": "agent@example.com",
        },
    }


PAGE_KEYS = [
    ("title", "string"),
    ("summary", "string"),
    ("elements", "array"),
    ("meta", "object"),
    ("meta.price", "number"),
    ("meta.compare_at", "number"),
    ("meta.name", "string"),
    ("meta.summary", "string"),
    ("meta.rating", "number"),
    ("rating", "number"),
    ("discount", "number"),
    ("reviews", "array"),
]

CART_KEYS = [
    ("title", "string"),
    ("summary", "string"),
    ("elements", "array"),
    ("meta", "object"),
    ("meta.items", "array"),
    ("meta.products", "array"),
    ("meta.products[].price", "number"),
    ("meta.products[].name", "string"),
    ("rating", "number"),
    ("discount", "number"),
    ("reviews", "array"),
]


def build_default_endpoints() -> list[dict[str, Any]]:
    tote = {
        "title": "Field Tote",
        "summary": "A heavy canvas carryall for markets, beaches and the long way home.",
        "elements": [
            {"action_id": "nav.products", "label": "Shop", "type": "link"},
            {"action_id": "product.add:field-tote", "label": "Add Field Tote", "type": "button"},
        ],
        "meta": {
            "name": "Field Tote",
            "summary": "Made to go further.",
            "price": 68,
            "compare_at": 85,
            "rating": 4.7,
        },
        "rating": 4.7,
        "discount": 20,
        "reviews": [{"author": "Alex", "text": "Beautifully made.", "rating": 5}],
    }
    notebook = {
        "title": "Trail Notebook",
        "summary": "Pocket-size ruled notebook with a waterproof cover.",
        "elements": [
            {"action_id": "nav.products", "label": "Shop", "type": "link"},
            {
                "action_id": "product.add:trail-notebook",
                "label": "Add Trail Notebook",
                "type": "button",
            },
        ],
        "meta": {
            "name": "Trail Notebook",
            "summary": "Takes pencil, ink and a little rain.",
            "price": 18,
            "compare_at": 22,
            "rating": 4.6,
        },
        "rating": 4.6,
        "discount": 18,
        "reviews": [{"author": "Sam", "text": "Perfect pocket size.", "rating": 5}],
    }
    return [
        _page(
            "page.home",
            "Home page",
            "/",
            {
                "title": "Northline Goods",
                "summary": "Gear for slow weekends.",
                "elements": [
                    {"action_id": "nav.products", "label": "Shop", "type": "link"},
                    {"action_id": "nav.cart", "label": "Cart", "type": "link"},
                ],
                "meta": {"name": "Northline Goods", "summary": "Editorial outdoor gear.", "price": None},
                "rating": 4.8,
                "discount": 0,
                "reviews": [],
            },
            PAGE_KEYS,
        ),
        _page(
            "page.products",
            "Shop",
            "/products",
            {
                "title": "Shop — Northline Goods",
                "summary": "8 products available.",
                "elements": [
                    {"action_id": "product.view:field-tote", "label": "View Field Tote", "type": "link"},
                    {"action_id": "product.add:field-tote", "label": "Add Field Tote", "type": "button"},
                ],
                "meta": {"name": "Shop", "summary": "Full catalog", "price": None},
                "rating": 4.7,
                "discount": 0,
                "reviews": [],
            },
            PAGE_KEYS,
        ),
        _page(
            "page.product.field-tote",
            "Product: Field Tote",
            "/products/field-tote",
            tote,
            PAGE_KEYS,
            hide={"meta.price", "discount"},
        ),
        _page(
            "page.product.trail-notebook",
            "Product: Trail Notebook",
            "/products/trail-notebook",
            notebook,
            PAGE_KEYS,
        ),
        _page(
            "page.cart",
            "Cart",
            "/cart",
            {
                "title": "Cart — Northline Goods",
                "summary": "2 item(s) in cart.",
                "elements": [
                    {"action_id": "cart.checkout", "label": "Checkout", "type": "button"},
                    {"action_id": "cart.clear", "label": "Clear cart", "type": "button"},
                ],
                "meta": {
                    "items": ["field-tote", "trail-notebook"],
                    "products": [
                        {"name": "Field Tote", "price": 68},
                        {"name": "Trail Notebook", "price": 18},
                    ],
                },
                "rating": 0,
                "discount": 0,
                "reviews": [],
            },
            CART_KEYS,
            access=True,
        ),
        _action("action.nav.products", "Action: Shop", "nav.products"),
        _action("action.nav.cart", "Action: Cart", "nav.cart"),
        _action("action.nav.home", "Action: Home", "nav.home"),
        _action(
            "action.product.add.field-tote",
            "Action: Add Field Tote",
            "product.add:field-tote",
        ),
        _action(
            "action.product.add.trail-notebook",
            "Action: Add Trail Notebook",
            "product.add:trail-notebook",
        ),
        _action(
            "action.product.view.field-tote",
            "Action: View Field Tote",
            "product.view:field-tote",
        ),
        _action(
            "action.product.view.trail-notebook",
            "Action: View Trail Notebook",
            "product.view:trail-notebook",
        ),
        _action("action.cart.clear", "Action: Clear cart", "cart.clear"),
        _action("action.cart.checkout", "Action: Checkout", "cart.checkout"),
    ]


DEFAULT_ENDPOINTS = build_default_endpoints()


def ensure_endpoint_shape(endpoints: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Upgrade legacy endpoint rows to include field schemas."""
    by_id = {e["id"]: e for e in endpoints}
    defaults = {e["id"]: deepcopy(e) for e in DEFAULT_ENDPOINTS}
    out: list[dict[str, Any]] = []
    for eid, default in defaults.items():
        cur = by_id.get(eid)
        if not cur:
            out.append(default)
            continue
        merged = deepcopy(default)
        merged["agent_access"] = bool(cur.get("agent_access", True))
        # preserve visibility toggles when keys match
        if cur.get("response_fields"):
            vis = {
                f["key"]: f.get("agent_visible", True)
                for f in cur["response_fields"]
                if isinstance(f, dict) and f.get("key")
            }
            for f in merged["response_fields"]:
                if f["key"] in vis:
                    f["agent_visible"] = bool(vis[f["key"]])
        if cur.get("request_fields"):
            allowed = {
                f["key"]: f.get("agent_allowed", True)
                for f in cur["request_fields"]
                if isinstance(f, dict) and f.get("key")
            }
            for f in merged["request_fields"]:
                if f["key"] in allowed:
                    f["agent_allowed"] = bool(allowed[f["key"]])
        out.append(merged)
    return out
