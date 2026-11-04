# Live text check — Meta Model API

> Point-in-time evidence (2026-11-02) for text **`muse-spark-1.3`**. Still the text default; see `docs/MODELS.md` for current env.

Date: 2026-11-02. Branch `cursor/meta-llm-text-provider-5c18`. Base commit before this evidence file: `f6968a089aa7b10be0f780fc5d4f2fe19a7d4ade`.

No API key, Authorization header, or raw credential is in this file.

## Preflight

- `key_set=yes`
- `prefix_llm=yes` (`META_API_KEY` matches `LLM_*`)
- `GET https://api.meta.ai/v1/models` → HTTP 200
- Model ids: `muse-wonder-1.0`, `sam-3.1`, `muse-spark-1.3-contributor`, `muse-voice-transcribe-1.0`, `muse-spark-1.3`, `muse-image-1.0`, `muse-spark-1.2-contributor`, `muse-spark-1.2`, `muse-spark-1.1`
- `muse-spark-1.3` present: yes

Process env for the run (names only): `META_API_KEY` set. `LLM_PROVIDER`, `LLM_FALLBACK_PROVIDER`, `META_BASE_URL`, `META_MODEL`, `META_LLM_MODEL`, `META_PROVIDER`, `META_REASONING_EFFORT`, `META_TIMEOUT_SECONDS`, `META_MAX_RETRIES`, and `BASETEN_API_KEY` were unset. No repo `.env`.

Resolved text settings (no key): provider `meta`, model `muse-spark-1.3`, base `https://api.meta.ai/v1`, timeout `8.0s`, max retries `1`, reasoning effort default `low`.

## Unit tests

```
cd server && python3 -m unittest discover -s tests -v
Ran 129 tests in 4.345s
OK
```

## Live calls

21 calls through the app functions (3 runs each). Handshake covers three purposes. Latency is wall time inside `muse_client.complete` (the call the 8s timeout bounds). Percentiles are nearest-rank: rank = ceil(p/100 * n).

| Section | Runs | Valid | Class ok | ReasoningOnly | Timeouts | p50 ms | p95 ms | max ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| handshake | 9 | 9 | 9 | 0 | 0 | 2205 | 5353 | 5353 |
| co-pilot (`propose_policy`) | 3 | 3 | 3 | 0 | 0 | 1898 | 2020 | 2020 |
| summary (`summarize_activity`) | 3 | 3 | 3 | 0 | 0 | 3399 | 3971 | 3971 |
| chat polish (`muse_browse._compose_reply`) | 3 | 3 | 3 | 0 | 0 | 1632 | 1809 | 1809 |
| page report (`_muse_report_site_response`) | 3 | 3 | 3 | 0 | 0 | 2608 | 2774 | 2774 |
| **all** | **21** | **21** | **21** | **0** | **0** | **2169** | **3971** | **5353** |

Provider and model on every call: `meta` / `muse-spark-1.3`. Source on every structured result: `model` (not keyword rules). p95 is under the 8s text timeout. No budget change is proposed.

Valid means a non-empty model result: handshake and co-pilot and summary have `source=model`, `degraded=false`, and the expected fields; chat polish and page report used the model reply (not the local fallback) and mentioned the given facts.

### Handshake (`score_purpose`)

| Purpose | Expected | Results |
|---|---|---|
| compare tote prices | high, drop act | high / drop_act true, all 3 |
| buy a tote | low, act allowed | low / drop_act false, all 3 |
| scrape all products | high, drop act | high / drop_act true, all 3 |

Latencies ms: 5353, 3320, 2662, 2377, 2205, 1396, 2015, 1250, 1758.

### Co-pilot (`propose_policy`)

Instruction: "hide prices from agents" on endpoint `page.product` with `meta.price`. All 3 returned a patch `meta.price` / `agent_visible: false` and a one-sentence summary. Latencies ms: 1711, 2020, 1898.

### Summary (`summarize_activity`)

Three events (1 handshake, 1 page read, 1 action, 1 agent). All 3 summaries stated those counts and did not invent blocks or high-risk agents. Latencies ms: 3971, 3399, 3357.

### Chat polish (`_compose_reply`)

Question "what is the price" with Name=Field Tote, Price=$48. All 3 replies: "The price is $48." Latencies ms: 1614, 1632, 1809.

### Page report (`_muse_report_site_response`)

All 3 replies named Field Tote and $48, with no HTTP/JSON jargon. Example: "I can see this product. Its name is Field Tote, price is $48." Latencies ms: 2608, 2774, 2169.

## `GET /api/health`

Flask was started locally on `127.0.0.1:8765` in the same process, after the live calls. HTTP **200**.

Text side:

- provider `meta`, model `muse-spark-1.3`, label `Muse Spark 1.3`, family `meta`, powered_by `Meta Muse Spark 1.3`
- base_url `https://api.meta.ai/v1`
- key_configured `true` (value not recorded)
- timeout_seconds `8.0`, max_retries `1`
- last_ok `true`, last_error `null`, degraded `false`, fallback `null`

Top-level body: `ok: true`, `degraded: true`, `partial: true`. That partial flag is the vision side on this branch (no vision key configured in that run; `key_configured: false`, `last_ok: null`). Vision was out of scope for that text-only PR.
