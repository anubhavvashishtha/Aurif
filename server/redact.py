"""JSON field redaction for agent responses (dotted paths + [] arrays)."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


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


def redact_response(payload: Any, response_fields: list[dict[str, Any]]) -> Any:
    result = deepcopy(payload)
    for field in response_fields:
        if field.get("agent_visible", True):
            continue
        key = field.get("key") or ""
        if key:
            omit_path(result, key.split("."))
    return result


def hidden_field_keys(response_fields: list[dict[str, Any]]) -> list[str]:
    return [f["key"] for f in response_fields if not f.get("agent_visible", True) and f.get("key")]
