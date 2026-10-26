# Aurif — Permissioned AI browsing for the open web

**One-liner:** Permissioned AI browsing for the open web.

## Two separate surfaces

| Surface | URL | Whose? |
|---------|-----|--------|
| **Customer website (demo)** | http://127.0.0.1:8787 | Fake merchant **Northline Goods** — normal human shop UI |
| **Aurif dashboard** | http://127.0.0.1:8787/dashboard | *Your* product — owners manage AI access & see agent activity |
| **Agent console** | http://127.0.0.1:8787/dashboard/agent-console.html | Aurif tooling to simulate a third-party AI agent |

The customer site does **not** link to the dashboard. Humans browse Northline like any store. AI agents do **not** scrape or click the human UI — they use machine endpoints only:

- `GET /.well-known/aurif.json`
- `POST /ai/handshake`
- `GET /ai/page`
- `POST /ai/actions`

**Demo owner login:** `owner@aurif.dev` / `demo1234`

## Flow to try

1. Open **Northline** as a human shopper — no Aurif chrome.
2. Open **Dashboard** as the site owner — toggle endpoints, watch activity.
3. Open **Agent console** (from the dashboard) — run an agent against `/ai/*` only.
4. Return to the dashboard — see which agent visited, which paths/actions it used.

## Quick start

```bash
cd server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

## Repo layout

```
demo/          Northline customer storefront (human UI)
dashboard/     Aurif product (owners + agent console)
sdk/aurif.js   Silent site plug + agent client
server/        Serves both + AI protocol + owner APIs
docs/          Product + protocol
```
