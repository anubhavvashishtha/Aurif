# Aurif MVP scope

Shipped in this repo as the first vertical slice of the product north star in [PRODUCT.md](PRODUCT.md).

## In scope

| Piece | Location | Behavior |
|-------|----------|----------|
| Locked pitch | [PRODUCT.md](PRODUCT.md), [README.md](../README.md) | One-liner + Google Docs analogy |
| Protocol `aurif-1` | [PROTOCOL.md](PROTOCOL.md) | Discovery, handshake, page, actions, audit |
| Site / agent SDK | [sdk/aurif.js](../sdk/aurif.js) | `discover`, `handshake`, `getPage`, `act`, DOM hooks |
| AI endpoints | [server/app.py](../server/app.py) | `/.well-known/aurif.json`, `/ai/*` |
| Owner store | [server/store.py](../server/store.py) | Accounts, sites, endpoint policy, activity |
| Owner dashboard | [dashboard/](../dashboard/) | Login, activity, endpoint toggles, credentials |
| Demo site | [demo/](../demo/) | Human shop UI + `/agent-demo` console |
| CLI agent | [examples/agent_cli.py](../examples/agent_cli.py) | Non-browser agent walkthrough |

**Demo owner:** `owner@aurif.dev` / `demo1234` → http://127.0.0.1:8787/dashboard

## Policy (MVP)

- Grant intersection of requested scopes with `view` / `act`.
- Reject agent id `blocked` (demo deny list).
- `act` required for add-to-cart, clear, checkout.
- Sessions expire after 1 hour; store is in-memory.

## Out of scope (later)

- Cryptographic agent identity / vendor registry
- Cross-site shared policy dashboard
- Rate limits and billing
- Persistent audit store
- Layout swaps for AI-only rendering
- Production auth for `/ai/audit`

## How to verify

```bash
cd server && source .venv/bin/activate && python app.py
# another terminal:
python3 examples/agent_cli.py
# browser: http://127.0.0.1:8787/agent-demo
```
