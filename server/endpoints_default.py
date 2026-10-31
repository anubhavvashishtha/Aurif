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
        "response_fields": [_rf(k, t, visible=(k not in hide)) for k, t in field_keys],
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


# Distinct schemas per real page type (not one shared PAGE_KEYS blob).
HOME_KEYS: list[tuple[str, str]] = [
    ("title", "string"),
    ("summary", "string"),
    ("elements", "array"),
    ("meta", "object"),
    ("meta.name", "string"),
    ("meta.summary", "string"),
]

SHOP_KEYS: list[tuple[str, str]] = [
    ("title", "string"),
    ("summary", "string"),
    ("elements", "array"),
    ("meta", "object"),
    ("meta.products", "array"),
    ("meta.products[].name", "string"),
    ("meta.products[].price", "number"),
    ("meta.products[].rating", "number"),
    ("meta.products[].href", "string"),
    ("meta.products[].slug", "string"),
    ("elements[].meta.price", "number"),
    ("elements[].meta.compare_at", "number"),
    ("elements[].meta.discount", "number"),
    ("elements[].meta.rating", "number"),
]

PRODUCT_KEYS: list[tuple[str, str]] = [
    ("title", "string"),
    ("summary", "string"),
    ("elements", "array"),
    ("meta", "object"),
    ("meta.name", "string"),
    ("meta.summary", "string"),
    ("meta.price", "number"),
    ("meta.compare_at", "number"),
    ("meta.rating", "number"),
    ("meta.sku", "string"),
    ("meta.highlights", "array"),
    ("rating", "number"),
    ("discount", "number"),
    ("reviews", "array"),
]

CART_KEYS: list[tuple[str, str]] = [
    ("title", "string"),
    ("summary", "string"),
    ("elements", "array"),
    ("meta", "object"),
    ("meta.items", "array"),
    ("meta.products", "array"),
    ("meta.products[].name", "string"),
    ("meta.products[].price", "number"),
]

# Legacy IDs collapsed into shared Product / product.* action templates.
LEGACY_PRODUCT_PAGE_IDS = (
    "page.product.field-tote",
    "page.product.trail-notebook",
)


def build_default_endpoints() -> list[dict[str, Any]]:
    product_sample = {
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
            "sku": "NL-TOTE",
            "highlights": ["waxed canvas", "brass hardware"],
        },
        "rating": 4.7,
        "discount": 20,
        "reviews": [{"author": "Alex", "text": "Beautifully made.", "rating": 5}],
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
                "meta": {"name": "Northline Goods", "summary": "Editorial outdoor gear."},
            },
            HOME_KEYS,
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
                "meta": {
                    "products": [
                        {
                            "name": "Field Tote",
                            "slug": "field-tote",
                            "price": 68,
                            "rating": 4.7,
                            "href": "/products/field-tote",
                        },
                        {
                            "name": "Trail Notebook",
                            "slug": "trail-notebook",
                            "price": 18,
                            "rating": 4.6,
                            "href": "/products/trail-notebook",
                        },
                    ]
                },
            },
            SHOP_KEYS,
        ),
        _page(
            "page.product",
            "Product page",
            "/products/*",
            product_sample,
            PRODUCT_KEYS,
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
            },
            CART_KEYS,
        ),
        _action("action.nav.products", "Action: Shop", "nav.products"),
        _action("action.nav.cart", "Action: Cart", "nav.cart"),
        _action("action.nav.home", "Action: Home", "nav.home"),
        _action("action.product.add", "Action: Add product", "product.add:*"),
        _action("action.product.view", "Action: View product", "product.view:*"),
        _action("action.cart.clear", "Action: Clear cart", "cart.clear"),
        _action("action.cart.checkout", "Action: Checkout", "cart.checkout"),
    ]


DEFAULT_ENDPOINTS = build_default_endpoints()


def _collect_visibility(rows: list[dict[str, Any]]) -> dict[str, bool]:
    vis: dict[str, bool] = {}
    for row in rows:
        for f in row.get("response_fields") or []:
            if isinstance(f, dict) and f.get("key"):
                # Prefer False if any legacy row hid the field.
                key = str(f["key"])
                visible = bool(f.get("agent_visible", True))
                if key not in vis:
                    vis[key] = visible
                else:
                    vis[key] = vis[key] and visible
    return vis


def _collect_request_allowed(rows: list[dict[str, Any]]) -> dict[str, bool]:
    allowed: dict[str, bool] = {}
    for row in rows:
        for f in row.get("request_fields") or []:
            if isinstance(f, dict) and f.get("key"):
                key = str(f["key"])
                ok = bool(f.get("agent_allowed", True))
                if key not in allowed:
                    allowed[key] = ok
                else:
                    allowed[key] = allowed[key] and ok
    return allowed


def ensure_endpoint_shape(endpoints: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Upgrade legacy endpoint rows to the real page-type schemas."""
    by_id = {e["id"]: e for e in endpoints if isinstance(e, dict) and e.get("id")}
    defaults = {e["id"]: deepcopy(e) for e in DEFAULT_ENDPOINTS}

    legacy_product_pages = [by_id[i] for i in LEGACY_PRODUCT_PAGE_IDS if i in by_id]
    # Also catch any other page.product.* rows that may have been added.
    for eid, row in by_id.items():
        if eid.startswith("page.product.") and eid != "page.product":
            if row not in legacy_product_pages:
                legacy_product_pages.append(row)

    legacy_add = [
        row
        for eid, row in by_id.items()
        if any(eid.startswith(p) for p in ("action.product.add.",))
        or row.get("action_id", "").startswith("product.add:")
    ]
    legacy_view = [
        row
        for eid, row in by_id.items()
        if any(eid.startswith(p) for p in ("action.product.view.",))
        or row.get("action_id", "").startswith("product.view:")
    ]

    product_vis = _collect_visibility(legacy_product_pages)
    if "page.product" in by_id:
        product_vis = {**product_vis, **_collect_visibility([by_id["page.product"]])}

    product_access = True
    for row in legacy_product_pages:
        if row.get("agent_access") is False:
            product_access = False
            break
    if "page.product" in by_id and by_id["page.product"].get("agent_access") is False:
        product_access = False

    add_access = all(bool(r.get("agent_access", True)) for r in legacy_add) if legacy_add else True
    if "action.product.add" in by_id:
        add_access = bool(by_id["action.product.add"].get("agent_access", add_access)) and add_access
    view_access = all(bool(r.get("agent_access", True)) for r in legacy_view) if legacy_view else True
    if "action.product.view" in by_id:
        view_access = bool(by_id["action.product.view"].get("agent_access", view_access)) and view_access

    add_req = _collect_request_allowed(legacy_add + ([by_id["action.product.add"]] if "action.product.add" in by_id else []))
    view_req = _collect_request_allowed(
        legacy_view + ([by_id["action.product.view"]] if "action.product.view" in by_id else [])
    )

    out: list[dict[str, Any]] = []
    for eid, default in defaults.items():
        merged = deepcopy(default)
        cur = by_id.get(eid)

        if eid == "page.product":
            merged["agent_access"] = product_access
            for f in merged["response_fields"]:
                if f["key"] in product_vis:
                    f["agent_visible"] = bool(product_vis[f["key"]])
        elif eid == "action.product.add":
            merged["agent_access"] = add_access
            for f in merged["request_fields"]:
                if f["key"] in add_req:
                    f["agent_allowed"] = bool(add_req[f["key"]])
        elif eid == "action.product.view":
            merged["agent_access"] = view_access
            for f in merged["request_fields"]:
                if f["key"] in view_req:
                    f["agent_allowed"] = bool(view_req[f["key"]])
        elif cur:
            merged["agent_access"] = bool(cur.get("agent_access", True))
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
