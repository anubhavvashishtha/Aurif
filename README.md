# Aurif

**Permissioned AI browsing for the open web.**

## Surfaces (keep separate)

| What | App | URL |
|------|-----|-----|
| Customer website (Northline Goods) | `Demo-client/` | http://127.0.0.1:5173 |
| Aurif owner dashboard + agent console | `Aurif-UI/` | http://127.0.0.1:5174 |
| AI protocol + owner APIs | `server/` | http://127.0.0.1:8787 |

Humans shop on Northline. AI agents use only `/.well-known/aurif.json` + `/ai/*` (no VLM / UI clicking). Owners control endpoint access and JSON field redaction in the dashboard.

**Demo login:** `owner@aurif.dev` / `demo1234`

## Run (3 terminals)

```bash
# 1) API
cd server
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app.py

# 2) Customer site
cd Demo-client && pnpm install && pnpm dev

# 3) Dashboard
cd Aurif-UI && pnpm install && pnpm dev
```

Node 22+ recommended (`nvm use 22`). Prefer `pnpm` (npm may fail on these Lovable lockfiles).

## Try the loop

1. Open Northline (5173) → solve the **human CAPTCHA** → shop.
2. Log into Aurif dashboard (5174) → hide `meta.price` / turn off an action.
3. Agent console → Handshake → Get page `/products/field-tote` → redacted fields omitted.
4. Run automated checks:

```bash
python3 examples/test_agents.py
```

Expect: UI scrapers **403**, Aurif agents see only allowed JSON.

## Repo layout

```
Demo-client/     Lovable Northline storefront
Aurif-UI/        Lovable Aurif dashboard
server/          Flask AI + owner APIs
sdk/aurif.js     Agent/site JS helper
docs/            Product + protocol notes
```
