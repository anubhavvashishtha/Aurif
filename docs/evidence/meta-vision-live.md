# Live vision check — Meta Model API

> Point-in-time evidence (2026-11-02), model **`muse-spark-1.3`**. Not the live demo default — current demo env often uses **`muse-wonder-1.0`** via `META_VISION_MODEL`. See `docs/MODELS.md`.

The first run used invalid shape targets (circle, house, star). This run uses character targets from `human_gate._LETTERS` and `_DIGITS`.

Date: 2026-11-02. Branch `cursor/meta-vision-muse-spark-18f2`. Base commit before this file was replaced: `9d9ddabb1b12478db8501188795a53eb31d45e21`.

No API key, Authorization header, or raw credential is in this file.

## Setup

Resolved vision settings (no key): provider `meta`, model `muse-spark-1.3`, base `https://api.meta.ai/v1`, timeout `15.0s`. `VISION_PROVIDER` was unset, so the Meta key selects Muse Spark.

Drawings are Pillow line strokes, not fonts. Canvas is 360×200, the UI pad (`clientWidth` fallback 360, height 200), paper `#fafaf8`. Strokes are 8px (inside the 6–10px range) with slight perpendicular jitter. Targets are from `_LETTERS` (`ABCDEFGHJKLMNPQRSTUVWXYZ`) and `_DIGITS` (`23456789`).

Each graded case ran twice. Two extra cases submit `human_gate._challenge_image(target)` as the drawing. Those are recorded, not graded: a typed challenge image should fail `human_like` or pass.

Latency is wall time inside `_complete_vision` (one call each; no fallback). Percentiles are nearest-rank: rank = ceil(p/100 * n). For the full set of 26, p95 is the second-slowest call.

## Results

Provider and model on every verdict: `meta` / `muse-spark-1.3`. Unreadable: 0. ReasoningOnly: 0. Timeouts: 0. Slowest call 9878 ms, under the 15s timeout.

| Case | Drawn | Target | Runs | Correct | ok | read_as | p50 ms | p95 ms |
|---|---|---|---:|---:|---|---|---:|---:|
| match letter | A | A | 2 | 2 | true, true | A, A | 1983 | 2070 |
| match letter | K | K | 2 | 2 | true, true | K, K | 2282 | 2498 |
| match digit | 4 | 4 | 2 | 1 | false, true | (empty), 4 | 3616 | 8547 |
| match digit | 7 | 7 | 2 | 2 | true, true | 7, 7 | 2716 | 3952 |
| match code | K4 | K4 | 2 | 2 | true, true | K4, K4 | 1709 | 3653 |
| match code | 7MN | 7MN | 2 | 2 | true, true | 7MN, 7MN | 1887 | 2314 |
| mismatch | H | A | 2 | 2 | false, false | H, H | 2026 | 2560 |
| mismatch | 7 | 4 | 2 | 2 | false, false | 7, 7 | 3712 | 4021 |
| mismatch | R | K | 2 | 2 | false, false | R, R | 2477 | 9878 |
| mismatch | H7 | K4 | 2 | 2 | false, false | H7, H7 | 2303 | 3907 |
| blank | (empty) | A | 2 | 2 | false, false | empty, empty | 2359 | 3377 |
| speck | 2px | 4 | 2 | 2 | false, false | empty, empty | 2326 | 4004 |
| challenge image | typed B | B | 1 | n/a | false | B | 3694 | 3694 |
| challenge image | typed R7 | R7 | 1 | n/a | false | R7 | 3156 | 3156 |

| Group | Correct | p50 ms | p95 ms | max ms |
|---|---:|---:|---:|---:|
| matches | 11/12 | 2314 | 8547 | 8547 |
| mismatches | 8/8 | 2560 | 9878 | 9878 |
| blank | 2/2 | 2359 | 3377 | 3377 |
| speck | 2/2 | 2326 | 4004 | 4004 |
| graded (no challenge images) | 23/24 | 2498 | 8547 | 9878 |
| all 26 calls | 23/24 graded | 2560 | 8547 | 9878 |

The failing match is digit `4`, run 1. `read_as` was empty, `human_like` true, `match` false, reason `sideways not upright 4`. The same glyph on run 2 passed with `read_as` `4`. No other match failed, and no match returned a wrong character in `read_as`.

Mismatches were read as the character that was drawn, not the target. Blank and speck were rejected as blank.

Both challenge images were read correctly (`B`, `R7`) and rejected as typed rather than hand-drawn (`human_like` false, `ok` false). Reasons: `typed B with extra scribble marks, not hand-drawn` and `typed not hand-drawn`.

## `GET /api/health`

Flask on `127.0.0.1:8767` in the same process, after the calls. HTTP **200**. Vision side: provider `meta`, model `muse-spark-1.3`, `key_configured` true, `timeout_seconds` 15.0, `last_ok` true, `last_error` null, `degraded` false.

## One miss (not applied)

Do not change the `read_as` equality check. The only miss left `read_as` empty because the model called an open 4 sideways, and the repeat of that glyph passed. If upright 4s keep failing on real pads, add one prompt line: a readable character that is a little tilted still counts, and `read_as` should be that character. No timeout change: p95 is 8547 ms.
