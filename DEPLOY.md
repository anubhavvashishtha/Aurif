# Deploy Aurif

Three services:

| Service | Code | Host | Local default |
|---------|------|------|----------------|
| Flask API | `server/` | **Render** (primary) | http://127.0.0.1:8787 |
| Customer storefront | `Demo-client/` | Vercel | http://127.0.0.1:5173 |
| Owner dashboard | `Aurif-UI/` | Vercel | http://127.0.0.1:5174 |

Railway can run the same API from `server/Procfile` if you set the service root to `server/`. Render is the primary because `render.yaml` pins Python, the gunicorn command, a health check, and a disk for `store.json`.

Local `python app.py` / `pnpm dev` still needs no env files. Copy the `.env.example` files only when you want overrides.

## Why Render

The blueprint in `render.yaml` is the production entry. It starts gunicorn (`server/Procfile` is the same command), sets `FLASK_DEBUG=0` and `AURIF_ENV=production` so the Werkzeug debugger stays off, and mounts a disk at `/var/data` for the JSON store. Gunicorn uses one worker because agent sessions and carts live in process memory; more workers would split that state.

## What you do by hand

No script can create these accounts.

1. A [Render](https://render.com) account that can pay for a Starter web service. The 1 GB disk in the blueprint is what keeps owner toggles and the site key across deploys. The free instance type has an ephemeral disk and cannot attach this disk.
2. A [Vercel](https://vercel.com) account and two projects from this repo (one per frontend).
3. One model key if the live demo must pass the drawing CAPTCHA or grant `act`. Prefer `MODEL_API_KEY` or `META_API_KEY` (Muse Spark 1.3 on the Meta Model API). If you do not have that key, `BASETEN_API_KEY` keeps Muse Spark Open for text and vision. Optional overrides are `META_MODEL`, `META_BASE_URL`, `META_VISION_*`, and `BASETEN_MODEL`. `MODAL_*` is not read. See [docs/MODELS.md](docs/MODELS.md).
4. After the API boots the first time, read the site key from the Render logs (`Site key → …`) unless you set `AURIF_SITE_KEY` before that boot.

## 1. API on Render

1. Push this branch. In Render: **New → Blueprint**, pick the repo, and apply `render.yaml`.
2. When Render asks for the `sync: false` variables, set:

   | Variable | Value |
   |----------|--------|
   | `AURIF_API_PUBLIC_URL` | The Render URL, e.g. `https://aurif-api.onrender.com` (no trailing slash) |
   | `CUSTOMER_SITE_URL` | The Vercel storefront URL once you have it |
   | `DASHBOARD_URL` | The Vercel dashboard URL once you have it |
   | `AURIF_CORS_ORIGINS` | Those two Vercel origins, comma-separated. Exact scheme + host. Not `*` |
   | `AURIF_SITE_KEY` | Optional long random string. Only used if `store.json` does not exist yet |
   | `MODEL_API_KEY` or `META_API_KEY` | Meta Model API key, if you have one. Leave blank to use Baseten |
   | `BASETEN_API_KEY` | Baseten key. Used only when neither Meta key is set |
   | `BASETEN_MODEL`, `META_MODEL`, `META_BASE_URL`, `META_VISION_*` | Optional. Defaults are in [docs/MODELS.md](docs/MODELS.md) |

3. Deploy. `GET /` should return JSON with `customer_site` and `dashboard` set to the public URLs, not `127.0.0.1`.
4. You can deploy the API before the frontends exist. Update the three URL variables and redeploy the API after Vercel assigns hostnames. CORS is read at process start.

`render.yaml` sets `plan: starter`. If the blueprint fails because the account has no payment method, either add one, or remove the `disk` block, the `plan` line, and `AURIF_STORE_PATH`, then deploy a free web service. See the disk section below before you demo on that free service.

### Railway instead

1. New service from this repo. **Root directory: `server`**. Config file: `server/Procfile` (gunicorn on `0.0.0.0:$PORT`, one worker, 120s timeout).
2. Set the same env vars as the table above. Also set `AURIF_ENV=production` and `FLASK_DEBUG=0`.
3. Attach a volume and set `AURIF_STORE_PATH` to a file on that volume (for example `/data/store.json`). Do not mount the volume on top of `server/data` — that directory also holds `catalog.json`, which ships in git.

## 2. Frontends on Vercel

Create **two** projects. For each one, set the root directory and leave the framework preset as TanStack Start (`vercel.json` sets `"framework": "tanstack-start"`). Do not set an output directory. Nitro writes `.vercel/output` when `VERCEL=1`, which Vercel sets during the build.

Vercel installs with **pnpm** because each app has `pnpm-lock.yaml`. That path does not hit the npm 10 bug. `engines.node` asks for Node 22+.

| Project root | Env vars |
|--------------|----------|
| `Demo-client` | `VITE_AURIF_API` = API origin. `VITE_AURIF_UI` = dashboard origin. `AURIF_API_URL` = same API origin (SSR agent gate; runtime). |
| `Aurif-UI` | `VITE_AURIF_API` = API origin. `VITE_CUSTOMER_SITE_URL` = storefront origin. |

`VITE_*` values are compiled into the browser bundle. Changing them requires a new Vercel deployment. `AURIF_API_URL` is read when the storefront server handles a request; set it on Production and Preview.

Use the production hostnames (`https://….vercel.app`), not a path. Preview deployments get a different origin each time. Add that origin to `AURIF_CORS_ORIGINS` and restart the API if you need the preview to call the API. A pattern such as `*.vercel.app` is not accepted.

### npm 10, if a build is switched to npm

`npm` 10.9 fails in these apps with `Cannot read properties of null (reading 'edgesOut')` (the `overrides.rolldown` field trips npm's arborist). Each app's `.npmrc` sets `legacy-peer-deps=true`, which avoids the crash. npm 11+ installs without that workaround. Prefer pnpm so the lockfile is used.

## 3. Order that works

1. Deploy the API with a placeholder CORS list if the Vercel URLs are not known yet.
2. Deploy both frontends with `VITE_AURIF_API` pointing at the Render URL.
3. Put the real Vercel origins in `CUSTOMER_SITE_URL`, `DASHBOARD_URL`, and `AURIF_CORS_ORIGINS`. Restart the API.
4. Redeploy both frontends once so each one links to the other's final URL (`VITE_AURIF_UI`, `VITE_CUSTOMER_SITE_URL`).
5. Open the dashboard, log in with `owner@aurif.dev` / `demo1234`, and confirm the customer-site link leaves the dashboard.

A browser request from a Vercel page sends a preflight. The API answers with that exact origin only when it is configured. `*` is ignored.

## `store.json` and ephemeral disks

`server/data/store.json` is gitignored. The first boot creates it and seeds:

- owner `owner@aurif.dev` / `demo1234`
- site `demo-shop` (Northline Goods) and its endpoint policy
- a random site key, or `AURIF_SITE_KEY` if that variable is set

The product catalog is `server/data/catalog.json`, which **is** in git. It is not the store. Do not point a disk mount at `server/data` or the catalog file disappears behind the empty volume.

What the store holds: owner accounts, the site key, endpoint toggles, and the activity log. Agent sessions and carts are in memory and already disappear when the process restarts. Say that in the demo if the API restarts mid-recording: the agent must handshake again. The owner login survives only if `store.json` is still there.

On an ephemeral disk (Render free, or any host that replaces the filesystem on deploy) the next boot does not see the old file, so it seeds again:

- the site key changes, unless `AURIF_SITE_KEY` was set before the seed
- endpoint toggles go back to the defaults
- accounts created in the UI are gone; the demo owner is recreated

`AURIF_SITE_KEY` is read only while the file is being created. It does not overwrite a key already in the file, so the dashboard "rotate key" control still works on a persistent disk. To reseed, delete the file and restart.

The blueprint stores the file at `/var/data/store.json` on a 1 GB disk. That disk survives deploys and restarts of the same service. It does not survive deleting the service.

## Env vars

### API (`server/`, repo-root `.env` locally)

| Name | Purpose |
|------|---------|
| `HOST` | Interface for `python app.py`. Default `127.0.0.1`. When `PORT` is set and `HOST` is not, the process binds `0.0.0.0`. Gunicorn binds `0.0.0.0:$PORT` itself. |
| `PORT` | Port. Default `8787`. Render and Railway inject this. Setting it also turns the debugger off unless `FLASK_DEBUG` is explicitly `1`. |
| `FLASK_DEBUG` | `1` or `0` for the Werkzeug debugger and reloader. `DEBUG` is an alias. Unset locally means on. |
| `AURIF_ENV` | `production` forces the debugger off. |
| `AURIF_API_PUBLIC_URL` | Public API origin returned to clients and used when Muse calls the API. `API_BASE` is an alias. Default `http://127.0.0.1:$PORT`. |
| `CUSTOMER_SITE_URL` | Storefront origin seeded into the demo site and returned by `GET /`. `STOREFRONT_URL` is an alias. Default `http://127.0.0.1:5173`. |
| `DASHBOARD_URL` | Dashboard origin returned by `GET /`. Default `http://127.0.0.1:5174`. |
| `AURIF_CORS_ORIGINS` | Comma-separated extra browser origins. `CORS_ORIGINS` is an alias. `*` is ignored. Localhost ports 5173 and 5174 stay allowed. The two public frontend URLs are added as well. |
| `AURIF_SITE_KEY` | Site key written when `store.json` is created. |
| `AURIF_STORE_PATH` | File path for the JSON store. Default `server/data/store.json`. |
| `MODEL_API_KEY` | Meta Model API key. Selects Muse Spark 1.3 for text and vision. |
| `META_API_KEY` | Alias of `MODEL_API_KEY`. If both are set, this one wins. |
| `BASETEN_API_KEY` | Used when no Meta key is set. Muse Spark Open for text and vision. Without any of the three keys, handshake drops `act` and CAPTCHA vision fails. |
| `BASETEN_MODEL` | Baseten model id. Default `meta-models/muse-spark-open-1026`. Only on the Baseten path. |
| `META_PROVIDER` | `meta`, or `baseten` when the Baseten key is the one in use. |
| `META_BASE_URL` | Default `https://api.meta.ai/v1`, or `https://inference.baseten.co/v1` on the Baseten path. |
| `META_MODEL` | Default `muse-spark-1.3`, or `BASETEN_MODEL` on the Baseten path. |
| `META_REASONING_EFFORT` | Default `low`. Sent only to the Meta Model API. |
| `META_VISION_API_KEY` | Vision key. Defaults to the text key. |
| `META_VISION_PROVIDER` | Vision provider. Defaults to the text provider. |
| `META_VISION_BASE_URL` | Vision base URL. Defaults to the text base URL. |
| `META_VISION_MODEL` | Vision model id. Defaults to the text model. |

`MODAL_VISION_MODEL`, `MODAL_BASE_URL`, `MODAL_TOKEN_ID`, and `MODAL_TOKEN_SECRET` are not read. A DeepSeek id in `BASETEN_MODEL` or `META_MODEL` is refused. Full notes: [docs/MODELS.md](docs/MODELS.md).

### Dashboard (`Aurif-UI/`)

| Name | Purpose |
|------|---------|
| `VITE_AURIF_API` | API origin for browser calls. Default `http://127.0.0.1:8787`. The dev server also proxies `/api`, `/ai`, and `/.well-known` at this origin. |
| `VITE_CUSTOMER_SITE_URL` | Storefront link, and the URL stored when a new owner signs up. Default `http://127.0.0.1:5173`. |

### Storefront (`Demo-client/`)

| Name | Purpose |
|------|---------|
| `VITE_AURIF_API` | API origin for the human-gate checks in the browser. Default `http://127.0.0.1:8787`. |
| `VITE_AURIF_UI` | Dashboard origin embedded as the human gate iframe. Default `http://127.0.0.1:5174`. |
| `AURIF_API_URL` | API origin for the SSR agent gate. Falls back to `VITE_AURIF_API`, then `http://127.0.0.1:8787`. |

## Production process

Do not use `python app.py` on the host. That path is the local debugger. Render's start command is:

```bash
gunicorn --bind 0.0.0.0:$PORT --workers 1 --timeout 120 app:app
```

The timeout is 120 seconds so a slow model call is not killed at gunicorn's 30 second default. One worker matches the in-memory session map.

## Without keys on the hosted demo

Same as local: humans cannot pass the drawing check, and handshake will not grant `act`. Log into the dashboard and turn human CAPTCHA off, or:

```bash
# TOKEN from POST /api/auth/login  {"email":"owner@aurif.dev","password":"demo1234"}
curl -s -X PATCH "$AURIF_API_PUBLIC_URL/api/sites/demo-shop" \
  -H "Content-Type: application/json" \
  -H "X-Aurif-Owner: $TOKEN" \
  -d '{"require_human_captcha":false}'
```

`product.add:*` still returns 403 until a Meta or Baseten key is set and handshake grants `act`.
