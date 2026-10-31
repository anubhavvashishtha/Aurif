# Models

Aurif calls one Meta model family for every LLM feature. The default is **Muse Spark 1.3** (`muse-spark-1.3`) on the **Meta Model API** (`https://api.meta.ai/v1`). That endpoint is OpenAI-compatible chat completions and accepts both text and images (base64 data URLs or public URLs), which is what the draw-CAPTCHA check sends.

Vision does not fall back to another vendor. A missing key, a DeepSeek model id, or an upstream error is returned as `vision provider misconfigured` / `vision provider error`.

## Why this host

| Option | Why it was or was not the default |
|--------|-----------------------------------|
| Meta Model API, `muse-spark-1.3` | **Default.** First-party Meta inference. Documented image understanding on chat completions, same shape the CAPTCHA path already uses. One key covers handshake risk, policy, activity polish, Muse phrasing, and vision. No extra GPU deploy for a four-day demo. |
| Baseten `meta-models/muse-spark-open` | Valid Meta weights (text, image, audio, video). Supported as an override. The public slug has 403'd on some hackathon participant keys; the older pin was `meta-models/muse-spark-open-1026`. Use it by setting `META_BASE_URL` and `META_MODEL`, not as a silent fallback. |
| Llama 4 Scout / Maverick, Llama 3.2 Vision | Meta open weights and vision-capable. Serving them means a second host (Llama API or Modal) and a second integration. Point `META_VISION_*` at that host if you already run one. Not the default, because Muse Spark 1.3 already covers both modalities. |
| Modal DeepSeek V4.1 Flash | Previous CAPTCHA model. Removed. Requests that name DeepSeek fail instead of calling it. |

`META_REASONING_EFFORT` defaults to `low` on `api.meta.ai` only. Muse Spark always reasons, and `none` is rejected by the API. Other hosts do not receive that field. Temperature is sent alone (Meta rejects temperature together with `top_p`). On the Meta Model API the output budget is raised to at least 768 tokens so reasoning does not consume a short `max_tokens` before the answer.

## Environment

Set one key. Everything else has a Meta default. Names only; do not commit secrets.

| Variable | Required | Default |
|----------|----------|---------|
| `MODEL_API_KEY` | yes, unless `META_API_KEY` is set | — |
| `META_API_KEY` | alias of `MODEL_API_KEY`; wins if both are set | — |
| `META_PROVIDER` | no | `meta` |
| `META_BASE_URL` | no | `https://api.meta.ai/v1` |
| `META_MODEL` | no | `muse-spark-1.3` |
| `META_VISION_API_KEY` | no | text key |
| `META_VISION_PROVIDER` | no | `META_PROVIDER` |
| `META_VISION_BASE_URL` | no | `META_BASE_URL` |
| `META_VISION_MODEL` | no | `META_MODEL` |
| `META_REASONING_EFFORT` | no | `low` (Meta Model API only) |

`MODAL_VISION_MODEL`, `MODAL_BASE_URL`, `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET`, `BASETEN_API_KEY`, and `BASETEN_MODEL` are no longer read.

Baseten override (still Muse, not DeepSeek):

```bash
META_PROVIDER=baseten
META_BASE_URL=https://inference.baseten.co/v1
META_MODEL=meta-models/muse-spark-open-1026
META_API_KEY=...
META_VISION_MODEL=meta-models/muse-spark-open
```

Use `meta-models/muse-spark-open` for vision when you can. That is the slug Baseten documents for image input. Keep `muse-spark-open-1026` for text only if the public slug returns 403 with a participant key.

## Audit

Searched `server/` (the only application code in this repo; `Aurif-UI/` and `Demo-client/` are empty gitlinks). No other chat-completions client, SDK, or HTTP call to an LLM host. `server/agent_gate.py` lists the substring `anthropic` as a bot user-agent to block. That is not a model call.

| Call site | Purpose | Before | Env before | After |
|-----------|---------|--------|------------|-------|
| `muse_client.score_purpose` → `complete` | Handshake purpose risk (`POST /ai/handshake`) | Baseten `meta-models/muse-spark-open-1026` | `BASETEN_API_KEY`, `BASETEN_MODEL`; base URL hardcoded to `https://inference.baseten.co/v1` | `META_MODEL` on `META_BASE_URL` (default `muse-spark-1.3` at `https://api.meta.ai/v1`) |
| `muse_client.propose_policy` → `complete` | Owner policy co-pilot (`POST /api/sites/<id>/ai/policy-propose`) | same Baseten Muse | same | same text endpoint |
| `muse_client.summarize_activity` → `complete` | Activity summary polish. Counts are computed locally in `_activity_brief`; the model only rewrites that draft (`POST /api/sites/<id>/ai/activity-summary`) | same Baseten Muse | same | same text endpoint |
| `muse_browse._compose_reply` → `complete` | One-sentence Muse dashboard answer when the page already returned the asked field | Dashboard model: Baseten Muse by default, or Modal DeepSeek if that id was selected | `BASETEN_*` or `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET`, `MODAL_BASE_URL`, `MODAL_VISION_MODEL` | same text endpoint. A non-Meta id in the request is rejected |
| `app._muse_report_site_response` → `complete` | Plain-English polish of a page the agent saw. Defined in `server/app.py`; no route calls it today | Baseten Muse | `BASETEN_*` | same text endpoint |
| `muse_client.verify_drawing` | Draw-CAPTCHA vision (`POST /api/public/human-verify`, and the dashboard bot path that posts there) | Modal `deepseek-ai/DeepSeek-V4.1-Flash`, then a silent fallback to Baseten Muse | `MODAL_BASE_URL`, `MODAL_VISION_MODEL`, `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET`; fallback used `BASETEN_API_KEY` and `BASETEN_MODEL` | `META_VISION_MODEL` on `META_VISION_BASE_URL`. No fallback |

Nothing was left on a non-Meta model. Local helpers (`_activity_brief`, field formatting, catalog JSON) are not model calls.

## Tests

`server/tests/test_meta_models.py` mocks the OpenAI client. No API key is required. From `server/`:

```bash
python -m unittest tests.test_meta_models
```
