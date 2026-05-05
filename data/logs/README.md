# data/logs/ — eval log inventory

Inspect-AI `.eval` logs accumulated across the thesis. Open with
`inspect view --log-dir data/logs/`.

## What's citable

The **post-FIX full matrix** (2 SUTs × 4 RAG tiers × 18 Phase-1 questions =
144 graded samples) reported in the root `README.md` derives from these
8 logs — one per (SUT × tier), each at 18/18 completed samples:

- `qwen3.5-397b-a17b` × 4 tiers → `2026-05-04T20-*` (4 logs, half-matrix
  rerun after the retry/resume hardening landed; the prior `2026-05-04T13/14-*`
  attempts hit transient gateway flakiness mid-run).
- `openai-gpt-oss-120b` × 4 tiers → `2026-05-05T08-*` (3 from the
  full N=6 background run, 1 from the T4 single-row retry after a
  gateway-side `ReadTimeout` on `Q-P1-CZ-09`).

Each `.eval`'s `eval.task_args.playback_jsonl` field points at the source
`data/diva_responses/<sut>__<tier>.jsonl` it replayed.

## What's not citable (and why)

| Date range | Task | Status | Why not |
|---|---|---|---|
| `2026-02-25T*`, `2026-03-23T*` | `union-benchmark` | retired | v0.1 axis-pipeline (Solidarity / Collectivism / Rights-awareness / Actionability + refusal class). Different schema, different scenarios, retired by the 2026-04-21 pivot. Preserved at git tag `v0.1-axis-pipeline`. |
| `2026-04-21T*` | `union-benchmark` | retired | Late axis-pipeline run. |
| `2026-04-28T*` | `legal-qa-benchmark` | confounded | CAPS-T08 baseline pilot. Pre-FIX — Arcana bypassed (missing SAIA gateway header). Cross-tier deltas are vLLM batch noise across no-op parameter values. Kept as evidence of the bug. |
| `2026-04-29T10-*`, `2026-04-29T12-*` | `legal-qa-benchmark` | confounded | v2 matrix at commit `8949ea9` plus diagnostic runs. Same Arcana-bypass bug. **Do not cite cross-tier deltas.** |
| `2026-04-29T14-42-32-*` | `legal-qa-benchmark` | failed | Pre-FIX smoke run from the *partial* `scripts/_run_diva.py` SAIA-header patch (header added, but no streaming yet — hit the gateway's ~10s ReadTimeout). Kept as evidence of the partial-patch state. |
| `2026-05-04T13-*`, `2026-05-04T14-*` | `legal-qa-benchmark` | smokes + experiment | Post-FIX, but small-N smokes (1–4 questions, validating the pipeline) plus the qwen3-30b-a3b grader experiment that was reverted (zero cross-tier discrimination — see vault `daily/2026-05-04.md`). Not part of the canonical matrix. |

## Methodology disclosure

See the root `README.md` Results section footnote for the canonical
disclosure. Summary: the DIVA matrix at commit `8949ea9` measured raw
vLLM model output rather than Arcana-augmented DIVA RAG — the SAIA
gateway requires the `inference-service: saia-openai-gateway` header
to invoke retrieval, and the matrix didn't send it from 2026-04-15
through 2026-05-04. All cross-tier results published in the thesis
derive from post-FIX data only.
