"""JSON field redaction for agent responses (dotted paths + [] arrays).

This is the only choke point that decides which fields an agent may see.
Hiding a price field also removes compare-at and discount figures at every
depth, including list rows and element metadata that are not separate toggles.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

# Revealing any one of these lets an agent reconstruct the hidden price.
PRICE_SIGNAL_KEYS = frozenset({"price", "compare_at", "discount"})


def omit_path(value: Any, parts: list[str]) -> None:
    if not isinstance(value, dict) or not parts:
        return
    part, *rest = parts
    is_array = part.endswith("[]")
    key = part[:-2] if is_array else part
    if not rest:
        value.pop(key, None)
        return
    child = value.get(key)
    if is_array and isinstance(child, list):
        for item in child:
            omit_path(item, rest)
    elif child is not None:
        omit_path(child, rest)


def is_price_field(key: str) -> bool:
    leaf = (key or "").split(".")[-1]
    if leaf.endswith("[]"):
        leaf = leaf[:-2]
    return leaf == "price"


def fields_hide_price(response_fields: list[dict[str, Any]] | None) -> bool:
    for field in response_fields or []:
        if field.get("agent_visible", True):
            continue
        if is_price_field(str(field.get("key") or "")):
            return True
    return False


def _deep_omit_keys(value: Any, keys: frozenset[str]) -> None:
    if isinstance(value, dict):
        for key in list(value.keys()):
            if key in keys:
                value.pop(key, None)
            else:
                _deep_omit_keys(value[key], keys)
    elif isinstance(value, list):
        for item in value:
            _deep_omit_keys(item, keys)


def redact_agent_payload(
    payload: Any,
    response_fields: list[dict[str, Any]] | None = None,
    *extra_field_lists: list[dict[str, Any]] | None,
) -> Any:
    """Remove hidden fields from one agent payload.

    Dotted paths are applied from ``response_fields`` only. Extra lists are
    consulted solely for the price policy: if any of them hides a price, price,
    compare_at, and discount are stripped everywhere in the payload.
    """
    result = deepcopy(payload)
    primary = list(response_fields or [])
    lists = [primary, *[list(fields or []) for fields in extra_field_lists]]
    for field in primary:
        if field.get("agent_visible", True):
            continue
        key = field.get("key") or ""
        if key:
            omit_path(result, str(key).split("."))
    if any(fields_hide_price(fields) for fields in lists):
        _deep_omit_keys(result, PRICE_SIGNAL_KEYS)
    return result


def redact_response(
    payload: Any,
    response_fields: list[dict[str, Any]] | None = None,
    *extra_field_lists: list[dict[str, Any]] | None,
) -> Any:
    return redact_agent_payload(payload, response_fields, *extra_field_lists)


def hidden_field_keys(response_fields: list[dict[str, Any]]) -> list[str]:
    return [f["key"] for f in response_fields if not f.get("agent_visible", True) and f.get("key")]


def price_link_fields(endpoints: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Hidden price toggles from page endpoints, used to redact embedded products."""
    linked: list[dict[str, Any]] = []
    for endpoint in endpoints or []:
        if endpoint.get("kind") != "page":
            continue
        for field in endpoint.get("response_fields") or []:
            if not isinstance(field, dict):
                continue
            key = str(field.get("key") or "")
            if field.get("agent_visible", True) or not is_price_field(key):
                continue
            linked.append({"key": key, "agent_visible": False})
    return linked
