#!/usr/bin/env python3
"""Minimal Aurif AI agent: discover → handshake → page → act."""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.parse
import urllib.request

PROTOCOL = "aurif-1"


def call(base: str, method: str, path: str, body: dict | None = None, token: str | None = None):
    url = base.rstrip("/") + path
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"X-Aurif-Protocol": PROTOCOL, "Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["X-Aurif-Session"] = token
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req) as res:
        return json.loads(res.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Aurif demo agent")
    parser.add_argument("--base", default="http://127.0.0.1:8787")
    parser.add_argument("--agent-id", default="cli-agent")
    parser.add_argument("--scopes", default="view,act")
    args = parser.parse_args()

    scopes = [s.strip() for s in args.scopes.split(",") if s.strip()]

    discovery = call(args.base, "GET", "/.well-known/aurif.json")
    print("discover:", json.dumps(discovery, indent=2))

    handshake = call(
        args.base,
        "POST",
        discovery["handshake"],
        {
            "agent_id": args.agent_id,
            "agent_version": "0.1.0",
            "requested_scopes": scopes,
            "purpose": "CLI demo: browse and add a product",
        },
    )
    print("handshake:", json.dumps(handshake, indent=2))
    token = handshake["session_token"]

    page = call(args.base, "GET", "/ai/page?path=" + urllib.parse.quote("/"), token=token)
    print("page:", json.dumps(page, indent=2))

    if "act" in handshake.get("granted_scopes", []):
        action = call(
            args.base,
            "POST",
            "/ai/actions",
            {"action_id": "product.add:field-tote", "args": {}},
            token=token,
        )
        print("action:", json.dumps(action, indent=2))
    else:
        print("skipping act — view-only session")


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as e:
        print("HTTP", e.code, e.read().decode())
        raise SystemExit(1)
