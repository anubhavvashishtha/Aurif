# Models

Aurif uses two model paths.

- **Text** stays on a Meta model. `META_API_KEY` or `MODEL_API_KEY` selects **Muse Spark 1.3** (`muse-spark-1.3`) on the **Meta Model API** (`https://api.meta.ai/v1`). If neither Meta key is set and `BASETEN_API_KEY` is set, text uses Baseten **Muse Spark Open** (`BASETEN_MODEL`, default `meta-models/muse-spark-open-1026`) at `https://inference.baseten.co/v1`. Handshake risk, the policy co-pilot, activity summaries, and Muse chat all use this path. A DeepSeek id in `BASETEN_MODEL`, `META_MODEL`, or the agent chat model is refused and does not call the host.
- **Draw-CAPTCHA vision** is separate. `muse_client.verify_drawing` (behind `POST /api/public/human-verify`) defaults to **DeepSeek V4.1 Flash** (`deepseek-ai/DeepSeek-V4.1-Flash-1017`) on Baseten's OpenAI-compatible endpoint (`https://inference.baseten.co/v1`), using the existing `BASETEN_API_KEY`. It does not inherit the text model. It is not labelled as Meta.
- `python app.py` prints the active text and vision provider, model, label, family, and base URL at startup (the API key is not printed).

`MODAL_*` is not read. There is no Modal host and no silent fallback from DeepSeek to Muse Spark. A missing vision key, a timeout, or an upstream error is logged and shown on `GET /api/health` (HTTP 503 when degraded, no API key in the body). The same snapshot is on `GET /api/ai/models` as `health`, and `vision` is a separate card from the text `current` model. The agent dashboard and the human gate show that vision credit on its own.

## Timeouts and outages

| Variable | Default | Meaning |
|----------|---------|---------|
| `META_TIMEOUT_SECONDS` | `8` | Text call budget, in seconds (clamped to 0.2–60). Also used for vision when both vision timeout vars are unset |
| `META_VISION_TIMEOUT_SECONDS` | `15` | Vision call budget. Used when `VISION_TIMEOUT_SECONDS` is unset |
| `VISION_TIMEOUT_SECONDS` | unset | Optional vision budget. Wins over `META_VISION_TIMEOUT_SECONDS` when set |
| `META_MAX_RETRIES` | `1` | Extra attempts after the first, capped at 2. Read timeouts are not retried. Connection failures and HTTP 408/429/500/502/503/504 are |

Handshake risk scoring, when the model errors or times out, uses a keyword rule instead of hanging or stripping `act` from every agent. A clear shopping purpose can still receive `act`. Scraping, bypass, resale, and vague purposes stay view-only. The handshake body says `purpose_risk.source` is `rules`, `degraded` is true, and `fallback` is `keyword_rules`. The score also carries the configured text model (`id`, `provider`, `label`, `family`, `powered_by`) and `latency_ms`. The agent-facing `reason` does not include env var names. A separate `warning` says the model was unavailable.

Policy propose and activity summary use the same text client and the same timeout. If that call errors or times out, policy propose returns HTTP 200 with a keyword-rules draft (`fallback` `keyword_rules`) and activity summary returns HTTP 200 with the counted brief (`fallback` `activity_counts`). Both set `source` to `rules` and `degraded` to true. Neither path writes policy. The owner applies a proposal with a separate request. When the model text is used, the dashboard shows `Powered by Meta <model>` plus latency. A fallback credit says it is a fallback and does not name that line as Meta or show `0 ms`. Activity summaries are given the counts as structured facts. A reply is kept when every count it states matches those facts (digits or words, any order). A changed or invented count is discarded, and the raw reply is logged at debug with secrets removed.

CAPTCHA, when vision is unavailable: a typed `answer` matching the challenge, or a non-blank sketch from the drawing pad, opens the **human storefront only**. The response is `degraded: true` with `method` `typed_fallback` or `ink_fallback`, and it does not grant agent `act`. A blank image gets HTTP 403 with `fallback` instructions. A working vision model that rejects a drawing (wrong characters, a blank pad, or a scribble) does not take this path.

The vision judge is strict. `match` must be true, the strokes must be hand-drawn, and `read_as` must be the requested characters. A correct `read_as` does not override `match: false`. The string `"false"` does not count as true. A reason that starts with blank, scribble, wrong, or a similar rejection, or a confidence below 0.8, is a rejection.

## Why these hosts

| Option | Why it was or was not the default |
|--------|-----------------------------------|
| Meta Model API, `muse-spark-1.3` | **Text default when `MODEL_API_KEY` or `META_API_KEY` is set.** First-party Meta inference for handshake risk, policy, activity, and Muse chat. |
| Baseten `meta-models/muse-spark-open-1026` | **Text default when only `BASETEN_API_KEY` is set.** Same Meta weights the demo already calls. The public slug `meta-models/muse-spark-open` has 403'd on some participant keys, so the dated id stays the default. |
| Baseten `deepseek-ai/DeepSeek-V4.1-Flash-1017` | **Vision default.** OpenAI-compatible chat at `https://inference.baseten.co/v1` with `BASETEN_API_KEY`. Muse Spark was passing drawings that did not match the prompt. DeepSeek is the draw-CAPTCHA judge only. |
| Another vision model (SAM 3.1, Muse, Llama) | Set `VISION_MODEL`, `VISION_BASE_URL`, and `VISION_API_KEY` (or the matching `META_VISION_*` name when `VISION_*` is unset). No code change. A Meta model id is labelled Meta. Anything else is not. |
| Modal DeepSeek | Not used. `MODAL_*` is not read. |

`META_REASONING_EFFORT` defaults to `low` on `api.meta.ai` only. Muse Spark always reasons, and `none` is rejected by the API. Other hosts, including Baseten DeepSeek, do not receive that field. Temperature is sent alone (Meta rejects temperature together with `top_p`). On the Meta Model API the output budget is raised to at least 768 tokens so reasoning does not consume a short `max_tokens` before the answer.

## Environment

Names only; do not commit secrets.

Text uses one of the Meta or Baseten keys below. Vision uses `BASETEN_API_KEY` unless a vision key or a Meta vision host is configured.

| Variable | Required | Default |
|----------|----------|---------|
| `MODEL_API_KEY` | one of this, `META_API_KEY`, or `BASETEN_API_KEY` for text | — |
| `META_API_KEY` | alias of `MODEL_API_KEY`; wins if both Meta keys are set | — |
| `BASETEN_API_KEY` | text when no Meta key is set; vision by default | — |
| `BASETEN_MODEL` | no | `meta-models/muse-spark-open-1026` (text on the Baseten path only) |
| `META_PROVIDER` | no | `meta`, or `baseten` when the Baseten key is the text host |
| `META_BASE_URL` | no | `https://api.meta.ai/v1`, or `https://inference.baseten.co/v1` on the text Baseten path |
| `META_MODEL` | no | `muse-spark-1.3`, or `BASETEN_MODEL` on the text Baseten path |
| `VISION_MODEL` | no | `deepseek-ai/DeepSeek-V4.1-Flash-1017` |
| `VISION_BASE_URL` | no | `https://inference.baseten.co/v1` |
| `VISION_API_KEY` | no | see key order below |
| `VISION_PROVIDER` | no | inferred from the vision host (`baseten` for the default). A `meta` label is ignored when the model is not a Meta model |
| `META_VISION_MODEL` | no | used only when `VISION_MODEL` is unset |
| `META_VISION_BASE_URL` | no | used only when `VISION_BASE_URL` is unset |
| `META_VISION_API_KEY` | no | used only when `VISION_API_KEY` is unset |
| `META_VISION_PROVIDER` | no | used only when `VISION_PROVIDER` is unset |
| `META_REASONING_EFFORT` | no | `low` (Meta Model API only) |
| `META_TIMEOUT_SECONDS` | no | `8` |
| `META_VISION_TIMEOUT_SECONDS` | no | `15` |
| `VISION_TIMEOUT_SECONDS` | no | unset; falls through to `META_VISION_TIMEOUT_SECONDS` |
| `META_MAX_RETRIES` | no | `1` |

Vision key order: `VISION_API_KEY`, then `META_VISION_API_KEY`, then `BASETEN_API_KEY`. If the vision host is `api.meta.ai` (or the model id is a Muse/Llama model and the host is not Baseten), the Meta key is used before `BASETEN_API_KEY`, so pointing vision back at the Meta API does not need a second secret name. `VISION_*` wins over `META_VISION_*` when both are set.

`MODAL_VISION_MODEL`, `MODAL_BASE_URL`, `MODAL_TOKEN_ID`, and `MODAL_TOKEN_SECRET` are not read. A DeepSeek id in `BASETEN_MODEL` or `META_MODEL` is refused for text and does not change the vision model. Set `VISION_MODEL` to change vision.

An existing `.env` with only `BASETEN_API_KEY` (and optional `BASETEN_MODEL`) keeps text on Muse Spark Open and moves CAPTCHA vision to DeepSeek on the same Baseten host. Adding `MODEL_API_KEY` or `META_API_KEY` switches text to the Meta Model API and leaves vision on DeepSeek, still using `BASETEN_API_KEY`.

## Audit

Searched `server/`. No other chat-completions client, SDK, or HTTP call to an LLM host. `server/agent_gate.py` lists the substring `anthropic` as a bot user-agent to block. That is not a model call.

The dashboard reads `GET /api/ai/models` as `models[]` and `current` (text: `id`, `label`, `provider`, `default`) plus a separate `vision` card and `health`. Policy propose, activity summary, and agent chat still return the text `model`. A rejected drawing returns `error`, `verdict` (including `read_as`, `model`, `provider`, `label`, `family`, `powered_by`), and `agent_access`. When vision is down, human verify can return `degraded`, `method`, and `warning` instead of failing closed. `providers.text` and `providers.vision` are separate. `providers.baseten.base_url` remains. `providers.modal` stays absent. `GET /api/health` and `GET /api/public/gate` report the same split. DeepSeek's `powered_by` is `DeepSeek V4.1 Flash`, never `Meta`.

| Call site | Purpose | Before | Env before | After |
|-----------|---------|--------|------------|-------|
| `muse_client.score_purpose` → `complete` | Handshake purpose risk (`POST /ai/handshake`) | Baseten `meta-models/muse-spark-open-1026` | `BASETEN_API_KEY`, `BASETEN_MODEL`; base URL hardcoded to `https://inference.baseten.co/v1` | Meta Model API when `META_API_KEY` or `MODEL_API_KEY` is set; otherwise the same Baseten model via `BASETEN_API_KEY` / `BASETEN_MODEL`. Unchanged by the vision split |
| `muse_client.propose_policy` → `complete` | Owner policy co-pilot (`POST /api/sites/<id>/ai/policy-propose`). Model failure returns a keyword draft and does not apply it | same Baseten Muse | same | same text endpoint |
| `muse_client.summarize_activity` → `complete` | Activity summary polish. Counts are computed locally in `_activity_brief`; the model only rewrites that draft. Model failure returns the counted brief (`POST /api/sites/<id>/ai/activity-summary`) | same Baseten Muse | same | same text endpoint |
| `muse_browse._compose_reply` → `complete` | One-sentence Muse dashboard answer when the page already returned the asked field | Text Meta model. A non-Meta id in the request is rejected | text `META_*` / `BASETEN_*` | same text endpoint. A non-Meta id in the request is still rejected |
| `app._muse_report_site_response` → `complete` | Plain-English polish of a page the agent saw. Defined in `server/app.py`; no route calls it today | Text Meta model | text `META_*` / `BASETEN_*` | same text endpoint |
| `muse_client.verify_drawing` | Draw-CAPTCHA vision (`POST /api/public/human-verify`, and the dashboard bot path that posts there) | Same resolved endpoint as text, unless `META_VISION_*` was set. DeepSeek ids were refused | text key and model, or `META_VISION_*` | `VISION_MODEL` (default `deepseek-ai/DeepSeek-V4.1-Flash-1017`) at `VISION_BASE_URL` (default `https://inference.baseten.co/v1`) with `BASETEN_API_KEY`. `META_VISION_*` still applies when the matching `VISION_*` var is unset. Non-Meta ids are allowed on this call only. Timeout, one retry, and the storefront-only degraded path are unchanged |

Text calls stay on a Meta model. Vision is the DeepSeek path above. Local helpers (`_activity_brief`, field formatting, catalog JSON) are not model calls.

## Tests

`server/tests/test_meta_models.py` mocks the OpenAI client. It checks that a non-matching, blank, or scribbled drawing is rejected, a matching drawing passes, the vision request uses `VISION_MODEL` and the Baseten URL, text calls still use the Meta model, and a non-Meta id is still refused for text. `server/tests/test_owner_ai.py` covers the owner handshake, policy, and activity endpoints, including the fallback path. No API key is required. From `server/`:

```bash
python -m unittest discover -s tests -v
```
