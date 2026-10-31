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

| Surface | Folder | Port | What it is |
|---------|--------|------|------------|
| **Customer website** (Northline Goods) | `Demo-client/` | [http://127.0.0.1:5173](http://127.0.0.1:5173) | Human storefront — shop, cart, human CAPTCHA gate |
| **Owner dashboard** | `Aurif-UI/` | [http://127.0.0.1:5174](http://127.0.0.1:5174) | Login, endpoints, Muse agent chat, activity |
| **API** | `server/` | [http://127.0.0.1:8787](http://127.0.0.1:8787) | Flask — `/ai/*`, owner APIs, Muse, CAPTCHA, store |

```
Aurif/
├── Demo-client/   # Northline — humans shop here
├── Aurif-UI/      # Aurif dashboard — owners + Muse demo agent
├── server/        # Protocol + policy + Muse backend
├── docs/          # Extra product / protocol notes
└── .env           # API keys (gitignored)
```

Keep the three surfaces separate on purpose: customer site ≠ owner console ≠ AI API.

**Demo login:** `owner@aurif.dev` / `demo1234`

---

## How to run

Need **Node 22+** (prefer `pnpm`) and **Python 3.11+**.

### 1. Env (repo root)

```bash
# .env (gitignored) — see .env.example and docs/MODELS.md
# Either a Meta Model API key:
MODEL_API_KEY=…
# or the existing Baseten key (Muse Spark Open, text and vision):
BASETEN_API_KEY=…
# BASETEN_MODEL=meta-models/muse-spark-open-1026
```

### 2. Three terminals

```bash
# Terminal 1 — API
cd server
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app.py
# → http://127.0.0.1:8787

# Terminal 2 — customer site
cd Demo-client && pnpm install && pnpm dev
# → http://127.0.0.1:5173

# Terminal 3 — dashboard
cd Aurif-UI && pnpm install && pnpm dev
# → http://127.0.0.1:5174
```

---

## What owners control

### Pages (read)

A **page** is the JSON snapshot an agent gets for a URL (`GET`-style via `POST /ai/page`).

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

### Quick action test (curl)

```bash
curl -s -X POST http://127.0.0.1:8787/ai/actions \
  -H "Content-Type: application/json" \
  -H "X-Aurif-Site-Key: YOUR_SITE_KEY" \
  -d '{"action_id":"product.add:field-tote","args":{"quantity":1}}'
```

Site key is on the dashboard (Settings / site detail).

---

## Models (hackathon)

Product AI runs in **server + Aurif-UI** (not Demo-client). Text and CAPTCHA vision both call a Meta model. With `MODEL_API_KEY` or `META_API_KEY`, that is **Muse Spark 1.3** on the Meta Model API (`https://api.meta.ai/v1`). With only `BASETEN_API_KEY`, text and vision stay on **Muse Spark Open** (`BASETEN_MODEL`, default `meta-models/muse-spark-open-1026`) at `https://inference.baseten.co/v1`. Startup prints which provider and model are active. A DeepSeek model id is refused. There is no Modal fallback.

| Feature | Where | Model |
|---------|--------|--------|
| Handshake purpose risk | `POST /ai/handshake` | active text model |
| Policy co-pilot | Endpoints | same |
| Activity summary | Activity | same |
| Muse chat phrasing | Agent dashboard | same |
| CAPTCHA vision | Human gate | active vision model (same as text unless `META_VISION_*` is set) |

See [docs/MODELS.md](docs/MODELS.md).

---

## Mental model

```
Human browser  →  Demo-client (:5173)  →  normal HTML shop + CAPTCHA
AI agent       →  server /ai/* (:8787) →  pages + actions under owner policy
Owner          →  Aurif-UI (:5174)     →  toggles, fields, Muse, activity
```
