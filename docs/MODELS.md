# Models

Aurif calls a Meta model for every LLM feature.

- `META_API_KEY` or `MODEL_API_KEY` selects **Muse Spark 1.3** (`muse-spark-1.3`) on the **Meta Model API** (`https://api.meta.ai/v1`). That endpoint is OpenAI-compatible chat completions and accepts images as base64 data URLs, which is what the draw-CAPTCHA check sends.
- If neither Meta key is set and `BASETEN_API_KEY` is set, text and vision both use Baseten **Muse Spark Open** (`BASETEN_MODEL`, default `meta-models/muse-spark-open-1026`) at `https://inference.baseten.co/v1`. The previous CAPTCHA path already sent drawing images to that model when Modal failed, so this keeps the current demo working.
- `python app.py` prints the active text and vision provider, model, and base URL at startup (the API key is not printed).

Vision does not fall back to a non-Meta vendor. `MODAL_*` is not read. A missing key, a timeout, or an upstream error is logged and shown on `GET /api/health` (HTTP 503 when degraded, no API key in the body). The same snapshot is on `GET /api/ai/models` as `health`, and the agent dashboard shows it.

## Timeouts and outages

| Variable | Default | Meaning |
|----------|---------|---------|
| `META_TIMEOUT_SECONDS` | `8` | Text call budget, in seconds (clamped to 0.2–60) |
| `META_VISION_TIMEOUT_SECONDS` | `15` | Vision call budget. Falls back to `META_TIMEOUT_SECONDS` when unset |
| `META_MAX_RETRIES` | `1` | Extra attempts after the first, capped at 2. Read timeouts are not retried. Connection failures and HTTP 408/429/500/502/503/504 are |

Handshake risk scoring, when the model errors or times out, uses a keyword rule instead of hanging or stripping `act` from every agent. A clear shopping purpose can still receive `act`. Scraping, bypass, resale, and vague purposes stay view-only. The handshake body says `purpose_risk.source` is `rules`, `degraded` is true, and `fallback` is `keyword_rules`. The score also carries the configured model (`id`, `provider`, `label`) and `latency_ms`. The agent-facing `reason` does not include env var names. A separate `warning` says the model was unavailable.

Policy propose and activity summary use the same client and the same timeout. If that call errors or times out, policy propose returns HTTP 200 with a keyword-rules draft (`fallback` `keyword_rules`) and activity summary returns HTTP 200 with the counted brief (`fallback` `activity_counts`). Both set `source` to `rules` and `degraded` to true. Neither path writes policy. The owner applies a proposal with a separate request. The dashboard labels the fallback and shows `Powered by Meta <model>` plus latency.

CAPTCHA, when vision is unavailable: a typed `answer` matching the challenge, or a non-blank sketch from the drawing pad, opens the **human storefront only**. The response is `degraded: true` with `method` `typed_fallback` or `ink_fallback`, and it does not grant agent `act`. A blank image gets HTTP 403 with `fallback` instructions. A working vision model that rejects a drawing does not take this path.

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

The dashboard reads `GET /api/ai/models` as `models[]` and `current` (`id`, `label`, `provider`, `default`) and now also `health`. Policy propose, activity summary, and agent chat still return `model` as a string or `{id, provider, label}`. A rejected drawing still returns `error`, `verdict.read_as`, and `agent_access`. When vision is down, human verify can return `degraded`, `method`, and `warning` instead of failing closed. `providers.baseten.base_url` remains. `providers.modal` stays absent.

| Call site | Purpose | Before | Env before | After |
|-----------|---------|--------|------------|-------|
| `muse_client.score_purpose` → `complete` | Handshake purpose risk (`POST /ai/handshake`) | Baseten `meta-models/muse-spark-open-1026` | `BASETEN_API_KEY`, `BASETEN_MODEL`; base URL hardcoded to `https://inference.baseten.co/v1` | Meta Model API when `META_API_KEY` or `MODEL_API_KEY` is set; otherwise the same Baseten model via `BASETEN_API_KEY` / `BASETEN_MODEL` |
| `muse_client.propose_policy` → `complete` | Owner policy co-pilot (`POST /api/sites/<id>/ai/policy-propose`). Model failure returns a keyword draft and does not apply it | same Baseten Muse | same | same text endpoint |
| `muse_client.summarize_activity` → `complete` | Activity summary polish. Counts are computed locally in `_activity_brief`; the model only rewrites that draft. Model failure returns the counted brief (`POST /api/sites/<id>/ai/activity-summary`) | same Baseten Muse | same | same text endpoint |
| `muse_browse._compose_reply` → `complete` | One-sentence Muse dashboard answer when the page already returned the asked field | Dashboard model: Baseten Muse by default, or Modal DeepSeek if that id was selected | `BASETEN_*` or `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET`, `MODAL_BASE_URL`, `MODAL_VISION_MODEL` | same text endpoint. A non-Meta id in the request is rejected |
| `app._muse_report_site_response` → `complete` | Plain-English polish of a page the agent saw. Defined in `server/app.py`; no route calls it today | Baseten Muse | `BASETEN_*` | same text endpoint |
| `muse_client.verify_drawing` | Draw-CAPTCHA vision (`POST /api/public/human-verify`, and the dashboard bot path that posts there) | Modal `deepseek-ai/DeepSeek-V4.1-Flash`, then a silent fallback to Baseten Muse | `MODAL_BASE_URL`, `MODAL_VISION_MODEL`, `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET`; fallback used `BASETEN_API_KEY` and `BASETEN_MODEL` | Same resolved endpoint as text, unless `META_VISION_*` is set. The old image fallback target (`BASETEN_MODEL`, default `meta-models/muse-spark-open-1026`) is the Baseten path. No DeepSeek call |

Nothing was left on a non-Meta model. Local helpers (`_activity_brief`, field formatting, catalog JSON) are not model calls.

## Tests

`server/tests/test_meta_models.py` mocks the OpenAI client. `server/tests/test_owner_ai.py` covers the owner handshake, policy, and activity endpoints, including the fallback path. No API key is required. From `server/`:

```bash
python -m unittest tests.test_meta_models
```
