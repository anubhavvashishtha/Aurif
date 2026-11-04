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
| `X-Aurif-Site-Key` | Agent | Site key. Required on handshake, page, actions, and audit. Also accepted as JSON `site_key` or `?site_key=`. |
| `X-Aurif-Session` | Agent (after handshake) | Session token from handshake. Required on page and actions. |
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

Denied scopes are omitted from `granted_scopes`. A missing or wrong site key → `403`. The JSON body may be empty: scopes then default to `["view"]` and a keyed handshake returns `200`. `requested_scopes` must be a list when it is sent (`400` otherwise). Policy reject → `403`.

## Page surface

`GET /ai/page?path=/`

Requires `X-Aurif-Site-Key` and `X-Aurif-Session` with `view`. The server does not implement `POST /ai/page`.

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
      "action_id": "product.add:field-tote",
      "type": "button",
      "label": "Add Field Tote to cart",
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
  "action_id": "product.add:field-tote",
  "args": {}
}
```

Response:

```json
{
  "ok": true,
  "result": { "cart": ["field-tote"] },
  "page": { "...": "optional refreshed snapshot" }
}
```

Unknown action → `404`. Insufficient scope → `403`.

## Audit

`GET /ai/audit` requires the site key. With `X-Aurif-Session`, events are limited to that session. Without a session header, the response includes recent events for the site.

Each event: `{ "ts", "session", "agent_id", "kind", "detail" }`.

## Help

`GET /ai/help` is open. It lists the fields agents must send. Every other agent call needs a matching site key.
