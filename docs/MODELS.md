# Models

Aurif calls a Meta model for every LLM feature.

- `META_API_KEY` or `MODEL_API_KEY` selects **Muse Spark 1.3** (`muse-spark-1.3`) on the **Meta Model API** (`https://api.meta.ai/v1`). That endpoint is OpenAI-compatible chat completions and accepts images as base64 data URLs, which is what the draw-CAPTCHA check sends.
- If neither Meta key is set and `BASETEN_API_KEY` is set, text and vision both use Baseten **Muse Spark Open** (`BASETEN_MODEL`, default `meta-models/muse-spark-open-1026`) at `https://inference.baseten.co/v1`. The previous CAPTCHA path already sent drawing images to that model when Modal failed, so this keeps the current demo working.
- `python app.py` prints the active text and vision provider, model, and base URL at startup (the API key is not printed).

Vision does not fall back to a non-Meta vendor. A missing key, a DeepSeek model id, or an upstream error is returned as `vision provider misconfigured` / `vision provider error`. `MODAL_*` is not read.

## Why this host

| Option | Why it was or was not the default |
|--------|-----------------------------------|
| Meta Model API, `muse-spark-1.3` | **Preferred when `MODEL_API_KEY` or `META_API_KEY` is set.** First-party Meta inference. Documented image understanding on chat completions, same shape the CAPTCHA path already uses. |
| Baseten `meta-models/muse-spark-open-1026` | **Used when only `BASETEN_API_KEY` is set.** Same Meta weights the demo already calls. The public slug `meta-models/muse-spark-open` has 403'd on some participant keys, so the dated id stays the default. The old vision fallback posted images to this id. |
| Llama 4 Scout / Maverick, Llama 3.2 Vision | Meta open weights and vision-capable. Serving them means a second host (Llama API or Modal) and a second integration. Point `META_VISION_*` at that host if you already run one. Not the default, because Muse Spark 1.3 already covers both modalities. |
| Modal DeepSeek V4.1 Flash | Previous CAPTCHA model. Removed. Requests that name DeepSeek fail instead of calling it. |

`META_REASONING_EFFORT` defaults to `low` on `api.meta.ai` only. Muse Spark always reasons, and `none` is rejected by the API. Other hosts do not receive that field. Temperature is sent alone (Meta rejects temperature together with `top_p`). On the Meta Model API the output budget is raised to at least 768 tokens so reasoning does not consume a short `max_tokens` before the answer.

## Environment

Set one key. Names only; do not commit secrets.

| Variable | Required | Default |
|----------|----------|---------|
| `MODEL_API_KEY` | one of this, `META_API_KEY`, or `BASETEN_API_KEY` | — |
| `META_API_KEY` | alias of `MODEL_API_KEY`; wins if both Meta keys are set | — |
| `BASETEN_API_KEY` | used when no Meta key is set | — |
| `BASETEN_MODEL` | no | `meta-models/muse-spark-open-1026` (only on the Baseten path) |
| `META_PROVIDER` | no | `meta`, or `baseten` when the Baseten key is the one in use |
| `META_BASE_URL` | no | `https://api.meta.ai/v1`, or `https://inference.baseten.co/v1` on the Baseten path |
| `META_MODEL` | no | `muse-spark-1.3`, or `BASETEN_MODEL` on the Baseten path |
| `META_VISION_API_KEY` | no | text key |
| `META_VISION_PROVIDER` | no | text provider |
| `META_VISION_BASE_URL` | no | text base URL |
| `META_VISION_MODEL` | no | text model |
| `META_REASONING_EFFORT` | no | `low` (Meta Model API only) |

`MODAL_VISION_MODEL`, `MODAL_BASE_URL`, `MODAL_TOKEN_ID`, and `MODAL_TOKEN_SECRET` are not read. A DeepSeek id in `BASETEN_MODEL` or `META_MODEL` is refused and does not call the host.

An existing `.env` with only `BASETEN_API_KEY` (and optional `BASETEN_MODEL`) keeps working for text and CAPTCHA vision. Adding `MODEL_API_KEY` or `META_API_KEY` switches the default host to the Meta Model API. `META_*` still overrides host and model on either path.

## Audit

Searched `server/`. No other chat-completions client, SDK, or HTTP call to an LLM host. `server/agent_gate.py` lists the substring `anthropic` as a bot user-agent to block. That is not a model call.

`Aurif-UI/` and `Demo-client/` on PR #1 (`cursor/import-frontend-sources-c904`) were checked and not merged here. The dashboard reads `GET /api/ai/models` as `models[]` and `current`, each with `id`, `label`, `provider`, and optional `default`. It does not read `providers`. Policy propose, activity summary, and agent chat still return `model` as a string or `{id, provider, label}`. Human verify still returns `error`, and on a rejected drawing `verdict.read_as` plus `agent_access`. Those fields are unchanged. `providers.text` and `providers.vision` are additions. `providers.baseten.base_url` is kept from the previous payload. `providers.modal` is removed because it was the DeepSeek URL and no frontend reads it.

| Call site | Purpose | Before | Env before | After |
|-----------|---------|--------|------------|-------|
| `muse_client.score_purpose` → `complete` | Handshake purpose risk (`POST /ai/handshake`) | Baseten `meta-models/muse-spark-open-1026` | `BASETEN_API_KEY`, `BASETEN_MODEL`; base URL hardcoded to `https://inference.baseten.co/v1` | Meta Model API when `META_API_KEY` or `MODEL_API_KEY` is set; otherwise the same Baseten model via `BASETEN_API_KEY` / `BASETEN_MODEL` |
| `muse_client.propose_policy` → `complete` | Owner policy co-pilot (`POST /api/sites/<id>/ai/policy-propose`) | same Baseten Muse | same | same text endpoint |
| `muse_client.summarize_activity` → `complete` | Activity summary polish. Counts are computed locally in `_activity_brief`; the model only rewrites that draft (`POST /api/sites/<id>/ai/activity-summary`) | same Baseten Muse | same | same text endpoint |
| `muse_browse._compose_reply` → `complete` | One-sentence Muse dashboard answer when the page already returned the asked field | Dashboard model: Baseten Muse by default, or Modal DeepSeek if that id was selected | `BASETEN_*` or `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET`, `MODAL_BASE_URL`, `MODAL_VISION_MODEL` | same text endpoint. A non-Meta id in the request is rejected |
| `app._muse_report_site_response` → `complete` | Plain-English polish of a page the agent saw. Defined in `server/app.py`; no route calls it today | Baseten Muse | `BASETEN_*` | same text endpoint |
| `muse_client.verify_drawing` | Draw-CAPTCHA vision (`POST /api/public/human-verify`, and the dashboard bot path that posts there) | Modal `deepseek-ai/DeepSeek-V4.1-Flash`, then a silent fallback to Baseten Muse | `MODAL_BASE_URL`, `MODAL_VISION_MODEL`, `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET`; fallback used `BASETEN_API_KEY` and `BASETEN_MODEL` | Same resolved endpoint as text, unless `META_VISION_*` is set. The old image fallback target (`BASETEN_MODEL`, default `meta-models/muse-spark-open-1026`) is the Baseten path. No DeepSeek call |

Nothing was left on a non-Meta model. Local helpers (`_activity_brief`, field formatting, catalog JSON) are not model calls.

## Tests

`server/tests/test_meta_models.py` mocks the OpenAI client. No API key is required. From `server/`:

```bash
python -m unittest tests.test_meta_models
```
