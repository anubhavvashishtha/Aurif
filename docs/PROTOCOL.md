# Aurif handshake & AI surface protocol (MVP)

Version: `aurif-1`

## Goals

1. Let an AI agent declare itself to a site.
2. Issue a scoped session token.
3. Expose a machine-friendly page snapshot and action API.
4. Keep the human UI unchanged.

## Headers

| Header | Who sets it | Meaning |
|--------|-------------|---------|
| `X-Aurif-Agent` | Agent | Agent product id, e.g. `demo-agent/1.0` |
| `X-Aurif-Session` | Agent (after handshake) | Session token from handshake |
| `X-Aurif-Protocol` | Both | Protocol version, `aurif-1` |

## Discovery

`GET /.well-known/aurif.json`

```json
{
  "protocol": "aurif-1",
  "name": "Aurif demo shop",
  "handshake": "/ai/handshake",
  "page": "/ai/page",
  "actions": "/ai/actions",
  "audit": "/ai/audit",
  "scopes_supported": ["view", "act"]
}
```

## Handshake

`POST /ai/handshake`

Request:

```json
{
  "agent_id": "demo-agent",
  "agent_version": "1.0",
  "requested_scopes": ["view", "act"],
  "purpose": "Help user browse products and add one to cart"
}
```

Response `200`:

```json
{
  "ok": true,
  "session_token": "…",
  "granted_scopes": ["view", "act"],
  "expires_in": 3600,
  "ai_surface": {
    "page": "/ai/page",
    "actions": "/ai/actions"
  }
}
```

Denied scopes are omitted from `granted_scopes`. Missing or invalid body → `400`. Policy reject → `403`.

## Page surface

`GET /ai/page?path=/`

Requires `X-Aurif-Session` with `view`.

Returns a structured snapshot: title, path, visible text, and interactive elements with stable `action_id`s — not a full HTML dump.

```json
{
  "path": "/",
  "title": "Aurif Demo Shop",
  "summary": "A small demo store for permissioned AI browsing.",
  "elements": [
    {
      "action_id": "nav.products",
      "type": "link",
      "label": "Products",
      "href": "/products"
    },
    {
      "action_id": "product.add:widget",
      "type": "button",
      "label": "Add Widget to cart",
      "scopes": ["act"]
    }
  ]
}
```

## Actions

`POST /ai/actions`

Requires `X-Aurif-Session` with `act` (or `view` for read-only navigations).

```json
{
  "action_id": "product.add:widget",
  "args": {}
}
```

Response:

```json
{
  "ok": true,
  "result": { "cart": ["widget"] },
  "page": { "...": "optional refreshed snapshot" }
}
```

Unknown action → `404`. Insufficient scope → `403`.

## Audit

`GET /ai/audit` (demo admin; MVP returns recent events for the session or site).

Each event: `{ "ts", "session", "agent_id", "kind", "detail" }`.

## Help

`GET /ai/help` is open. It lists the fields agents must send. Every other agent call needs a matching site key.
