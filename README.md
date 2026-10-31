# Aurif

**Permissioned AI browsing for the open web.**

Owners decide what AI agents can **read** and **do** on a site — as structured JSON and named actions — instead of letting bots scrape HTML or click the UI blindly.

---

## Idea in short

Today, agents either:

- scrape the public HTML (no permission model), or
- drive a browser like a human (fragile, opaque).

**Aurif** sits in between:

1. The site publishes an AI surface (`/.well-known/aurif.json` + `/ai/*`).
2. Agents call that API with a **site key**.
3. Owners use the dashboard to turn **pages** and **actions** on/off, and to hide specific JSON fields (e.g. price).
4. Humans still use the normal storefront. Agents do not need to click pixels to shop the catalog — they use the protocol (optional Muse chat in the dashboard can also browse the live site to demo CAPTCHA / gate behavior).

**ORF framing (one line):** *Open, permissioned agent access — owners control the machine-readable surface of their site the way they already control robots.txt, but for structured pages and actions.*

---

## Where things live

| Surface | Folder | Local URL | What it is |
|---------|--------|-----------|------------|
| **Customer website** (Northline Goods) | `Demo-client/` | [http://127.0.0.1:5173](http://127.0.0.1:5173) | Human storefront — shop, cart, human CAPTCHA gate |
| **Owner dashboard** | `Aurif-UI/` | [http://127.0.0.1:5174](http://127.0.0.1:5174) | Login, endpoints, Muse agent chat, activity |
| **API** | `server/` | [http://127.0.0.1:8787](http://127.0.0.1:8787) | Flask — `/ai/*`, owner APIs, Muse, CAPTCHA, store |

Those URLs are the local defaults. Override them with the variables in `.env.example` when you need to.

```
Aurif/
├── Demo-client/   # Northline — humans shop here
├── Aurif-UI/      # Aurif dashboard — owners + Muse demo agent
├── server/        # Protocol + policy + Muse backend
├── docs/          # Extra product / protocol notes
└── .env.example   # Copy to .env for keys (gitignored once copied)
```

Keep the three surfaces separate on purpose: customer site ≠ owner console ≠ AI API.

**Demo login:** `owner@aurif.dev` / `demo1234`

---

## How to run

Need **Node 22+** and **Python 3.11+**. No `.env` is required to boot. Copy [`.env.example`](.env.example) to `.env` only when you have model keys.

The API process reads the **repo-root** `.env` (and `server/.env` if you add one). Run it from `server/` so the local imports resolve.

### 1. API

```bash
cd server
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

The log prints the API URL, the demo login, and the site key (`Site key → …`). CLI calls need that key. It is also on the dashboard after you log in. With no env set, the API listens on `127.0.0.1:8787` with the debugger on.

### 2. Customer site and dashboard

Prefer **pnpm** (each app commits a `pnpm-lock.yaml`):

```bash
# Terminal 2 — customer site → http://127.0.0.1:5173
cd Demo-client && pnpm install && pnpm dev

# Terminal 3 — dashboard → http://127.0.0.1:5174
cd Aurif-UI && pnpm install && pnpm dev
```

If you use npm: **npm 10 fails** with `Cannot read properties of null (reading 'edgesOut')`. Use **npm 11+**, or npm 10 with `npm install --legacy-peer-deps`. Both apps set `legacy-peer-deps=true` in `.npmrc`, so a plain `npm install` works on npm 10 as well. Then `npm run dev`.

### Without model keys

The API still starts. With no `MODEL_API_KEY`, `META_API_KEY`, or `BASETEN_API_KEY`, model calls fail closed into a keyword and ink fallback. `GET /api/health` returns 503 while that is true.

- **Drawing CAPTCHA.** A typed match of the challenge characters, or a sketch with visible ink, opens the human storefront only. It does not grant agent `act`. A blank pad still fails.
- **`act` scope.** Handshake risk uses keyword rules. A shopping purpose (`buy`, `cart`, `browse`, and similar) can still receive `act`. A vague purpose, or one that looks like scraping, stays view-only, so `product.add:*` returns 403 `scope 'act' not granted`.

Turn the human gate off for a local walkthrough (owner token from the login response):

```bash
curl -s -X POST http://127.0.0.1:8787/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"owner@aurif.dev","password":"demo1234"}'

curl -s -X PATCH http://127.0.0.1:8787/api/sites/demo-shop \
  -H 'Content-Type: application/json' \
  -H "X-Aurif-Owner: TOKEN_FROM_LOGIN" \
  -d '{"require_human_captcha":false}'
```

Browsing pages with `view` works without keys. Adding to the cart still works for a shopping purpose when keyword rules grant `act`. A vague or scraping purpose does not.

Set **one** key in the repo-root `.env`. See [`.env.example`](.env.example) and [docs/MODELS.md](docs/MODELS.md).

- `MODEL_API_KEY` or `META_API_KEY` — Muse Spark 1.3 on the Meta Model API for text (handshake, policy, activity, Muse chat).
- Or `BASETEN_API_KEY` alone — Muse Spark Open (`BASETEN_MODEL`, default `meta-models/muse-spark-open-1026`) for text.
- The same `BASETEN_API_KEY` is the draw-CAPTCHA vision key. Vision defaults to DeepSeek V4.1 Flash (`VISION_MODEL`, default `deepseek-ai/DeepSeek-V4.1-Flash-1017`) at `https://inference.baseten.co/v1`. It does not follow the text model. Optional `VISION_*` and `META_VISION_*` overrides are in `docs/MODELS.md`.

`MODAL_*` is not read. A DeepSeek model id is refused for text and is the vision default. Startup prints the active provider and model (not the key).

---

## What owners control

### Pages (read)

A **page** is the JSON snapshot an agent gets for a URL (`GET /ai/page?path=`). There is no `POST /ai/page`.

| Endpoint | Path | Rough shape |
|----------|------|-------------|
| Home | `/` | title, summary, elements, `meta.name` / `meta.summary` |
| Shop | `/products` | catalog in `meta.products[]` |
| Product | `/products/*` | one shared product template (price, sku, reviews, …) |
| Cart | `/cart` | `meta.items`, `meta.products[]` |

Toggle **agent access** off → agents get **403** for that page.  
**Configure fields** → hide dotted paths (e.g. `meta.price`) from the agent JSON while the owner still sees the full sample.

### Actions (do)

An **action** is something the agent may **invoke** (`POST /ai/actions`) — not HTML scraping.

| Action | Meaning |
|--------|---------|
| `nav.home` / `nav.products` / `nav.cart` | Navigate |
| `product.view:*` / `product.add:*` | Open or add any product |
| `cart.clear` / `cart.checkout` | Cart mutations |

Turn an action off → call is blocked, and that control is removed from page `elements`.  
Configure fields on actions = mostly **request** allowlists (quantity, args, email) plus a small response (`ok`, `summary`, `result`).

---

## Try the loop

1. **Human:** open Northline (5173) → pass CAPTCHA → browse / cart.
2. **Owner:** login dashboard (5174) → **Endpoint control** → flip pages/fields/actions.
3. **Agent:** **Agent dashboard** → optional site key → ask Muse to open shop / add Field Tote.
4. **Audit:** **Activity** → each handshake, page, action, allow/deny.

Without a matching site key (when the site requires one), protocol calls are denied. With a key, the agent only receives the JSON and actions the owner left open.

### Quick page test (curl)

This works on a fresh boot with no model keys. The site key is the `Site key →` line from `python app.py` (and on the dashboard after login). Handshake first; `/ai/actions` and `/ai/page` both require `X-Aurif-Session`.

```bash
KEY='paste-site-key'

curl -s -X POST http://127.0.0.1:8787/ai/handshake \
  -H 'Content-Type: application/json' \
  -H "X-Aurif-Site-Key: $KEY" \
  -d '{"requested_scopes":["view"],"purpose":"browse the catalog"}'
# copy session_token from the JSON

curl -s "http://127.0.0.1:8787/ai/page?path=/products" \
  -H "X-Aurif-Site-Key: $KEY" \
  -H "X-Aurif-Session: SESSION_TOKEN"
```

`POST /ai/actions` with `product.add:field-tote` also needs that session header, the site key, and a handshake that granted `act`. A shopping purpose still can, including when the model is down and keyword rules score the purpose. A vague or scraping purpose does not. Without the session the API returns 401 `missing or invalid session`.

---

## Models (hackathon)

Product AI runs in **server + Aurif-UI** (not Demo-client). Text calls a Meta model. With `MODEL_API_KEY` or `META_API_KEY`, that is **Muse Spark 1.3** on the Meta Model API (`https://api.meta.ai/v1`). With only `BASETEN_API_KEY`, text stays on **Muse Spark Open** (`BASETEN_MODEL`, default `meta-models/muse-spark-open-1026`) at `https://inference.baseten.co/v1`. Draw-CAPTCHA vision is **DeepSeek V4.1 Flash** (`deepseek-ai/DeepSeek-V4.1-Flash-1017`) on that same Baseten endpoint, using `BASETEN_API_KEY`. Health and the dashboard show the two models separately. DeepSeek is not labelled as Meta. Startup prints which provider and model are active. Calls time out (`META_TIMEOUT_SECONDS`, default 8s; vision `META_VISION_TIMEOUT_SECONDS`, default 15s) and do not retry a hung read. If the model is down, handshake risk uses keyword rules (shopping purposes can still get `act`; vague or scraping purposes stay view-only) and the human gate accepts a typed code or a non-blank sketch for the storefront only. `GET /api/health` reports the failure. A DeepSeek model id is refused for text. There is no Modal fallback.

| Feature | Where | Model |
|---------|--------|--------|
| Handshake purpose risk | `POST /ai/handshake` | active text model |
| Policy co-pilot | Endpoints | same |
| Activity summary | Activity | same |
| Muse chat phrasing | Agent dashboard | same |
| CAPTCHA vision | Human gate | DeepSeek V4.1 Flash on Baseten, unless `VISION_*` or `META_VISION_*` is set |

See [docs/MODELS.md](docs/MODELS.md).

---

## Mental model

```
Human browser  →  Demo-client (:5173)  →  normal HTML shop + CAPTCHA
AI agent       →  server /ai/* (:8787) →  pages + actions under owner policy
Owner          →  Aurif-UI (:5174)     →  toggles, fields, Muse, activity
```
