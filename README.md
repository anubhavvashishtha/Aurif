# Aurif

**Permissioned AI browsing for the open web.**

Owners decide what AI agents can **read** and **do** on a site — as structured JSON and named actions — instead of letting bots scrape HTML or click the UI blindly.

1. The site publishes an AI surface (`/.well-known/aurif.json` + `/ai/*`).
2. Agents call that API with a **site key**.
3. Owners use the dashboard to turn **pages** / **actions** on or off, and to hide JSON fields (e.g. price).
4. Humans keep the normal storefront. Agents use the protocol. The dashboard’s Muse chat can also browse the live shop to demo the CAPTCHA gate and the permissioned API.

---

## What you need

| Tool | Version |
|------|---------|
| **Node** | 22+ |
| **Python** | 3.11+ |
| **pnpm** | recommended (each app has a `pnpm-lock.yaml`) |

Model API keys are **optional** to boot the three surfaces. Without keys, the API still runs; handshake / Muse / CAPTCHA vision fall back to keyword and ink rules. See [Models](#models-optional) below.

---

## Repo layout

| Surface | Folder | Local URL | Role |
|---------|--------|-----------|------|
| Customer website (Northline Goods) | `Demo-client/` | http://127.0.0.1:5173 | Human storefront + CAPTCHA |
| Owner dashboard | `Aurif-UI/` | http://127.0.0.1:5174 | Login, endpoints, Muse chat, activity |
| API | `server/` | http://127.0.0.1:8787 | `/ai/*`, owner APIs, Muse, CAPTCHA, store |

```
Aurif/
├── Demo-client/   # Northline — humans shop here
├── Aurif-UI/      # Owner dashboard + Muse demo agent
├── server/        # Protocol, policy, Muse backend
├── docs/          # Protocol / product / models notes
└── .env.example   # Copy to .env for model keys (gitignored)
```

**Demo login:** `owner@aurif.dev` / `demo1234`

---

## Run locally (3 terminals)

Do this from a fresh clone. Keep all three processes running.

### 1. API (`:8787`)

```bash
cd server
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

You should see something like:

```text
Aurif API        → http://127.0.0.1:8787
Customer site    → http://127.0.0.1:5173
Aurif dashboard  → http://127.0.0.1:5174
Demo login       → owner@aurif.dev / demo1234
Site key         → …
```

Copy the **site key** if you will call `/ai/*` from curl or enable it in Muse chat. The same key appears in the dashboard after login.

Run the API from `server/` so imports resolve. It reads the **repo-root** `.env` (and `server/.env` if present). Defaults: `127.0.0.1:8787`, debugger off. Set `FLASK_DEBUG=1` only if you want the debugger.

### 2. Customer site (`:5173`)

```bash
cd Demo-client
pnpm install
pnpm dev
```

Open http://127.0.0.1:5173 — shop, product pages, cart, human CAPTCHA.

### 3. Owner dashboard (`:5174`)

```bash
cd Aurif-UI
pnpm install
pnpm dev
```

Open http://127.0.0.1:5174 — log in with the demo credentials above.

#### Using npm instead of pnpm

Both frontends set `legacy-peer-deps=true` in `.npmrc`. Prefer **npm 11+**, or on npm 10 run `npm install` (legacy peers already enabled) then `npm run dev`. Plain npm 10 without that flag can fail with `Cannot read properties of null (reading 'edgesOut')`.

---

## First walkthrough

1. **Human:** open http://127.0.0.1:5173 → pass the CAPTCHA → browse / add to cart.
2. **Owner:** open http://127.0.0.1:5174 → log in → **Endpoint control** → flip pages, fields (e.g. hide price), and actions.
3. **Agent:** **Agent** page → paste a product link and ask Muse (e.g. price / discount). With the site key on, after CAPTCHA fails the agent follows the “use the API with a site key” path and reads `/ai/page` under your field policy.
4. **Audit:** **Activity** → handshakes, page reads, allows / denies.

Turn the human CAPTCHA off for a quick local walkthrough (optional):

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8787/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"owner@aurif.dev","password":"demo1234"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

curl -s -X PATCH http://127.0.0.1:8787/api/sites/demo-shop \
  -H 'Content-Type: application/json' \
  -H "X-Aurif-Owner: $TOKEN" \
  -d '{"require_human_captcha":false}'
```

---

## Models (optional)

Copy [`.env.example`](.env.example) to a repo-root `.env`. **Do not commit `.env`.** Full matrix: [docs/MODELS.md](docs/MODELS.md).

Set **at least one** key for live models:

| Goal | Env |
|------|-----|
| Text (handshake, policy, Muse chat) via Meta | `META_API_KEY` or `MODEL_API_KEY` → Muse Spark 1.3 |
| Text via Baseten only | `BASETEN_API_KEY` → Muse Spark Open |
| Draw-CAPTCHA vision | Same Meta key by default; override with `META_VISION_MODEL` (e.g. `muse-wonder-1.0`) or `VISION_*` / Baseten |

Without keys the API still boots. `GET /api/health` reports text/vision health. Model calls fall closed to keyword / ink fallbacks (storefront CAPTCHA can still open for a typed match or non-blank sketch; agent `act` still depends on purpose scoring).

Startup logs print the active text and vision provider/model (never the key).

---

## What owners control

### Pages (read)

JSON snapshot for a URL: `GET /ai/page?path=…`

| Endpoint | Path |
|----------|------|
| Home | `/` |
| Shop | `/products` |
| Product | `/products/*` |
| Cart | `/cart` |

- **Agent access off** → agents get **403** for that page.
- **Hide fields** → dotted paths (e.g. `meta.price`) are omitted from agent JSON; the human site is unchanged.

### Actions (do)

Invoke via `POST /ai/actions` (not HTML scraping): navigate, `product.add:*`, cart clear/checkout, etc. Turn an action off → call blocked and control removed from page `elements`.

---

## Quick agent test (curl)

Works on a fresh boot. Use the `Site key →` line from `python app.py` (or the dashboard).

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

`POST /ai/actions` (e.g. `product.add:field-tote`) needs the same headers plus a handshake that granted `act` (shopping-style purpose). Without a session → `401`. Wrong or missing site key → refused.

Discovery: `GET http://127.0.0.1:8787/.well-known/aurif.json` and `GET /ai/help`.

---

## Mental model

```
Human browser  →  Demo-client (:5173)  →  HTML shop + CAPTCHA
AI agent       →  server /ai/* (:8787) →  pages + actions under owner policy
Owner          →  Aurif-UI (:5174)     →  toggles, fields, Muse, activity
```

More detail: [docs/PROTOCOL.md](docs/PROTOCOL.md), [docs/PRODUCT.md](docs/PRODUCT.md), [docs/MODELS.md](docs/MODELS.md).

Override ports and public URLs with the variables documented in [`.env.example`](.env.example) (`HOST`, `PORT`, `CUSTOMER_SITE_URL`, `DASHBOARD_URL`, `AURIF_API_PUBLIC_URL`, CORS).
