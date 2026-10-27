"""Load Northline catalog for AI page snapshots."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CATALOG_PATH = Path(__file__).resolve().parent / "data" / "catalog.json"


def load_catalog() -> dict[str, Any]:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def products_by_slug() -> dict[str, dict[str, Any]]:
    data = load_catalog()
    return {p["slug"]: p for p in data["products"]}


def public_product(p: dict[str, Any]) -> dict[str, Any]:
    compare = p.get("compareAt")
    price = p["price"]
    discount = 0
    if compare and compare > price:
        discount = round((1 - price / compare) * 100)
    return {
        "id": p["slug"],
        "slug": p["slug"],
        "name": p["name"],
        "tagline": p.get("tagline", ""),
        "summary": p.get("tagline") or (p.get("description") or [""])[0][:160],
        "description": p.get("description", []),
        "category": p.get("category"),
        "price": price,
        "compare_at": compare,
        "discount": discount,
        "sku": p.get("sku"),
        "rating": p.get("rating"),
        "review_count": p.get("reviewCount"),
        "stock": p.get("stock"),
        "highlights": p.get("highlights", [])[:6],
        "reviews": [
            {
                "author": r.get("name"),
                "rating": r.get("rating"),
                "title": r.get("title"),
                "text": r.get("body"),
            }
            for r in (p.get("reviews") or [])[:5]
        ],
    }
