# Models

Aurif uses two model paths.

- **Text** stays on a Meta model. `META_API_KEY` or `MODEL_API_KEY` selects **Muse Spark 1.3** (`muse-spark-1.3`) on the **Meta Model API** (`https://api.meta.ai/v1`). If neither Meta key is set and `BASETEN_API_KEY` is set, text uses Baseten **Muse Spark Open** (`BASETEN_MODEL`, default `meta-models/muse-spark-open-1026`) at `https://inference.baseten.co/v1`. Handshake risk, the policy co-pilot, activity summaries, and Muse chat all use this path. A DeepSeek id in `BASETEN_MODEL`, `META_MODEL`, or the agent chat model is refused and does not call the host.
- **Draw-CAPTCHA vision** is separate and does not inherit the text model. If `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET` are both set, vision calls **DeepSeek V4.1 Flash** on Modal (`MODAL_VISION_MODEL`, default `deepseek-ai/DeepSeek-V4.1-Flash`) at `MODAL_BASE_URL`. The OpenAI client key is `{MODAL_TOKEN_ID}.{MODAL_TOKEN_SECRET}`. The label is **DeepSeek V4.1 Flash (Modal)**. If those tokens are unset, `VISION_*` applies (kept for a later model such as SAM 3.1), then the Baseten default `deepseek-ai/DeepSeek-V4.1-Flash-1017` at `https://inference.baseten.co/v1` with `BASETEN_API_KEY`. It is not labelled as Meta.
- `python app.py` prints the active text and vision provider, model, label, family, and base URL at startup (the API key is not printed).

`VISION_FALLBACK_MODEL` is empty unless you set it. A 401, 403, 404, or model-not-found on the primary vision host then retries that model once, inside the same vision time budget. `VISION_FALLBACK_BASE_URL` and `VISION_FALLBACK_API_KEY` default to Baseten. The verify response names the model that actually judged. Other errors do not switch models. There is no Muse fallback unless you set one.

A 401, 403, 404, or model-not-found is logged and stored on the vision side of `GET /api/health` and `GET /api/ai/models` as `vision model <id>: 403 forbidden, check Modal model access or slug` (the host name follows the provider). The line names the provider and the model. It never includes the key or the CAPTCHA answer. A successful fallback leaves that primary error in `vision.last_error` while `vision.last_ok` stays true.

Health is per model. `text` and `vision` each have `degraded` and `last_error`. `GET /api/health` returns **200** when text is up, including a vision-only outage: `degraded` is true and `partial` is true. That is the same 200-plus-degraded shape the handshake, policy, and activity routes already use for a partial outage. **503** is only when text is down (`ok` is false). The dashboard banner is on every dashboard page and names the side that failed. A vision-only failure does not say handshakes left the model.

## Timeouts and outages

| Variable | Default | Meaning |
|----------|---------|---------|
| `META_TIMEOUT_SECONDS` | `8` | Text call budget, in seconds (clamped to 0.2–60). Also used for vision when both vision timeout vars are unset |
| `META_VISION_TIMEOUT_SECONDS` | `15` | Vision call budget. Used when `VISION_TIMEOUT_SECONDS` is unset |
| `VISION_TIMEOUT_SECONDS` | unset | Optional vision budget. Wins over `META_VISION_TIMEOUT_SECONDS` when set |
| `META_MAX_RETRIES` | `1` | Extra attempts after the first, capped at 2. Read timeouts are not retried. Connection failures and HTTP 408/429/500/502/503/504 are |

Handshake risk scoring, when the model errors or times out, uses a keyword rule instead of hanging or stripping `act` from every agent. A clear shopping purpose can still receive `act`. Scraping, bypass, resale, and vague purposes stay view-only. The handshake body says `purpose_risk.source` is `rules`, `degraded` is true, and `fallback` is `keyword_rules`. The score also carries the configured text model (`id`, `provider`, `label`, `family`, `powered_by`) and `latency_ms`. The agent-facing `reason` does not include env var names. A separate `warning` says the model was unavailable.

Policy propose and activity summary use the same text client and the same timeout. If that call errors or times out, policy propose returns HTTP 200 with a keyword-rules draft (`fallback` `keyword_rules`) and activity summary returns HTTP 200 with the counted brief (`fallback` `activity_counts`). Both set `source` to `rules` and `degraded` to true. Neither path writes policy. The owner applies a proposal with a separate request. When the model text is used, the dashboard shows `Powered by Meta <model>` plus latency. A fallback credit says it is a fallback and does not name that line as Meta or show `0 ms`. Every Muse text call (handshake, browse polish, policy co-pilot, activity summary, owner page report) sends `reasoning_effort` `low` on hosts other than `api.meta.ai`, plus the open-weight `chat_template_kwargs` form. A 400 on that field is retried once without it. `api.meta.ai` already sends `reasoning_effort` `low`. The text timeout stays 8 seconds. Only `message.content` is the reply. A response that is only reasoning is logged as `model returned only reasoning` and falls back; that path does not log `model unavailable (model request failed)`. On Baseten the output budgets are handshake 2048, browse polish 1024, owner page report 1024, activity summary 2048, and policy co-pilot 2500. Activity summaries are given the counts as structured facts. A reply is kept when every count it states matches those facts (digits or words, any order). Digits inside version strings and agent ids are not counts, and a number does not bind across a sentence. A changed or invented count is discarded. The reject reason and the offending phrase are logged at warning, and the raw reply is logged at debug with secrets removed.

CAPTCHA, when vision is unavailable: a typed `answer` matching the challenge, or a non-blank sketch from the drawing pad, opens the **human storefront only**. The response is `degraded: true` with `method` `typed_fallback` or `ink_fallback`, and it does not grant agent `act`. A blank image gets HTTP 403 with `fallback` instructions. That object has no `target` field, and the prompt does not repeat the characters. A working vision model that rejects a drawing (wrong characters, a blank pad, a scribble, or a speck too small to be a character) does not take this path. The reject `error` is `drawing did not match` and does not echo the model reason or the expected characters.

The vision judge is strict. `match` must be true, the strokes must be hand-drawn, and `read_as` must be the requested characters. A correct `read_as` does not override `match: false`. The string `"false"` does not count as true. A reason that starts with blank, scribble, wrong, or a similar rejection, or a confidence below 0.8, is a rejection. A positive match on a drawing whose ink is only a few pixels, or whose stroke is shorter than 12 pixels on the long side, is rejected.

## Why these hosts

| Option | Why it was or was not the default |
|--------|-----------------------------------|
| Meta Model API, `muse-spark-1.3` | **Text default when `MODEL_API_KEY` or `META_API_KEY` is set.** First-party Meta inference for handshake risk, policy, activity, and Muse chat. |
| Baseten `meta-models/muse-spark-open-1026` | **Text default when only `BASETEN_API_KEY` is set.** Same Meta weights the demo already calls. The public slug `meta-models/muse-spark-open` has 403'd on some participant keys, so the dated id stays the default. |
| Modal `deepseek-ai/DeepSeek-V4.1-Flash` | **Vision provider when `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET` are set.** Same `{token_id}.{token_secret}` API key the earlier Modal client used. Label: DeepSeek V4.1 Flash (Modal). |
| Baseten `deepseek-ai/DeepSeek-V4.1-Flash-1017` | **Vision default when Modal tokens are unset.** OpenAI-compatible chat at `https://inference.baseten.co/v1` with `BASETEN_API_KEY`. A 403 from this slug on a key that can call Muse is an account entitlement, not a bad id. |
| Another vision model (SAM 3.1, Muse, Llama) | Leave Modal unset and set `VISION_MODEL`, `VISION_BASE_URL`, and `VISION_API_KEY` (or the matching `META_VISION_*` name when `VISION_*` is unset). No code change. A Meta model id is labelled Meta. Anything else is not. |
| `VISION_FALLBACK_MODEL` | Optional, empty by default. One retry after 401/403/404 or model-not-found. Example: `meta-models/muse-spark-open-1026` on Baseten. |

`META_REASONING_EFFORT` defaults to `low` on `api.meta.ai` only. Muse Spark always reasons, and `none` is rejected by the API. Every other Muse text call sends `reasoning_effort` `low` and `chat_template_kwargs.reasoning_effort` `low`, and retries once without those fields on HTTP 400. Temperature is sent alone (Meta rejects temperature together with `top_p`). On the Meta Model API the output budget is raised to at least 768 tokens so reasoning does not consume a short `max_tokens` before the answer. Baseten sends the requested budget: handshake 2048, browse polish 1024, owner page report 1024, activity summary 2048, policy co-pilot 2500. The answer is `message.content` only.

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
| `MODAL_TOKEN_ID` | both this and `MODAL_TOKEN_SECRET` to use Modal | — |
| `MODAL_TOKEN_SECRET` | both tokens, or Modal is not selected | — |
| `MODAL_BASE_URL` | no | `https://anubhavvashishtha-iitd--ep-deepseek-v4-1-flash-server.us-west.modal.direct/v1` |
| `MODAL_VISION_MODEL` | no | `deepseek-ai/DeepSeek-V4.1-Flash` |
| `VISION_FALLBACK_MODEL` | no | unset (no fallback) |
| `VISION_FALLBACK_BASE_URL` | no | `https://inference.baseten.co/v1` |
| `VISION_FALLBACK_API_KEY` | no | `BASETEN_API_KEY` |

Vision host order: Modal when both token vars are set, otherwise `VISION_*` / `META_VISION_*`, otherwise Baseten DeepSeek. Vision key order on the non-Modal path: `VISION_API_KEY`, then `META_VISION_API_KEY`, then `BASETEN_API_KEY`. If the vision host is `api.meta.ai` (or the model id is a Muse/Llama model and the host is not Baseten), the Meta key is used before `BASETEN_API_KEY`. `VISION_*` wins over `META_VISION_*` when both are set. Modal's key is always `{MODAL_TOKEN_ID}.{MODAL_TOKEN_SECRET}` and is not logged.

A DeepSeek id in `BASETEN_MODEL` or `META_MODEL` is refused for text and does not change the vision model.

An existing `.env` with only `BASETEN_API_KEY` keeps text on Muse Spark Open and CAPTCHA vision on Baseten DeepSeek. Adding the two Modal tokens switches vision to Modal and leaves text where it was. Adding `MODEL_API_KEY` or `META_API_KEY` switches text to the Meta Model API.

## Audit

Searched `server/`. No other chat-completions client, SDK, or HTTP call to an LLM host. `server/agent_gate.py` lists the substring `anthropic` as a bot user-agent to block. That is not a model call.

The dashboard reads `GET /api/ai/models` as `models[]` and `current` (text: `id`, `label`, `provider`, `default`) plus a separate `vision` card and `health`. Policy propose, activity summary, and agent chat still return the text `model`. A rejected drawing returns a generic `error` (`drawing did not match`), `verdict` (including `model`, `provider`, `label`, `family`, `powered_by`; `read_as` is blank when it repeats the answer), and `agent_access`. When vision is down, human verify can return `degraded`, `method`, and `warning` instead of failing closed. The blank-drawing `fallback` prompt does not include the answer. `providers.text` and `providers.vision` are separate. `providers.baseten.base_url` remains. `providers.modal` is present only while Modal is the vision provider, and only as a base URL. `GET /api/health` returns 200 with `partial: true` when vision is down and text is up, and 503 when text is down. `GET /api/public/gate` still returns the text and vision cards, including Modal's label. Modal DeepSeek's `powered_by` is `DeepSeek V4.1 Flash (Modal)`. Baseten DeepSeek's is `DeepSeek V4.1 Flash`. Neither is `Meta`.

| Call site | Purpose | Before | Env before | After |
|-----------|---------|--------|------------|-------|
| `muse_client.score_purpose` → `complete` | Handshake purpose risk (`POST /ai/handshake`) | Baseten `meta-models/muse-spark-open-1026` | `BASETEN_API_KEY`, `BASETEN_MODEL`; base URL hardcoded to `https://inference.baseten.co/v1` | Meta Model API when `META_API_KEY` or `MODEL_API_KEY` is set; otherwise the same Baseten model via `BASETEN_API_KEY` / `BASETEN_MODEL`. Unchanged by the vision split |
| `muse_client.propose_policy` → `complete` | Owner policy co-pilot (`POST /api/sites/<id>/ai/policy-propose`). Model failure returns a keyword draft and does not apply it | same Baseten Muse | same | same text endpoint |
| `muse_client.summarize_activity` → `complete` | Activity summary polish. Counts are computed locally in `_activity_brief`; the model only rewrites that draft. Model failure returns the counted brief (`POST /api/sites/<id>/ai/activity-summary`) | same Baseten Muse | same | same text endpoint |
| `muse_browse._compose_reply` → `complete` | One-sentence Muse dashboard answer when the page already returned the asked field | Text Meta model. A non-Meta id in the request is rejected | text `META_*` / `BASETEN_*` | same text endpoint. A non-Meta id in the request is still rejected |
| `app._muse_report_site_response` → `complete` | Plain-English polish of a page the agent saw. Defined in `server/app.py`; no route calls it today | Text Meta model | text `META_*` / `BASETEN_*` | same text endpoint |
| `muse_client.verify_drawing` | Draw-CAPTCHA vision (`POST /api/public/human-verify`, and the dashboard bot path that posts there) | Baseten DeepSeek, or `VISION_*` / `META_VISION_*` | `VISION_*`, else Baseten | Modal when both `MODAL_TOKEN_*` vars are set (`deepseek-ai/DeepSeek-V4.1-Flash` by default). Otherwise the same `VISION_*` path, then Baseten DeepSeek. Optional `VISION_FALLBACK_MODEL` retries once on 401/403/404 or model-not-found. Text is unchanged |

Text calls stay on a Meta model. Vision is the DeepSeek path above. Local helpers (`_activity_brief`, field formatting, catalog JSON) are not model calls.

## Tests

`server/tests/test_meta_models.py` mocks the OpenAI client. It checks that Modal credentials send vision to Modal with the `token_id.token_secret` key and leave text on Meta, that unset Modal credentials still use `VISION_*`, that a 403 is named in the log and in health without the key, that `VISION_FALLBACK_MODEL` is one extra call only for an access error, that a tiny drawing fails a positive match, and that a non-Meta id is still refused for text. Health tests cover vision-down/text-up (HTTP 200, `partial`) and text-down/vision-up (HTTP 503). `server/tests/test_owner_ai.py` covers the owner handshake, policy, and activity endpoints, including the keyword-rules path. No API key is required. From `server/`:

```bash
python -m unittest discover -s tests -v
```
