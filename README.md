# Legal-QA Output-Quality Benchmark for DIVA

Master's thesis repository — Georg-August-Universität Göttingen.
Primary supervisor: Dr. Alexander Silbersdorff. Aligned with the KIBI/DIVA project (ver.di / Uni Göttingen / TU Clausthal / ver.di b+b).

## What this is

LLM evaluation against expert-authored German labor-law questions. A grader LLM
compares each model response to an expert reference answer and assigns a
3-level verdict:

- `worse_than_reference` — misses key reference points, contains legal errors, or hallucinates paragraphs/sources
- `on_par_with_reference` — covers the reference's substantive points, no major errors
- `better_than_reference` — covers the reference plus adds correct, relevant content

A binary `correct` is derived: `1.0` iff the verdict is `on_par` or `better`,
else `0.0`. Per-sample verdict + reasoning land in the `.eval` log alongside
the SUT output for inspection.

Substrate: the Phase-1+2 TESTFRAGEN corpus from DIVA testing (35
expert-authored questions; 18 carry reference answers and are scorable today,
17 are parked until expert references are commissioned).

## File layout

```
schema.py                                        Pydantic models (Question, Verdict, ModelEvaluation, DivaResponse)
inspect_benchmark.py                             Inspect AI task — the entry point. Contains both the
                                                 `legal_qa_benchmark` task (default frontier path) and the
                                                 `diva_playback` solver (replay precomputed DIVA responses)
judge_prompt.txt                                 German LLM-judge prompt (3-level verdict)
data/legal_qa/questions_with_reference.jsonl     18 Phase-1 records (scorable)
data/legal_qa/questions_pending_reference.jsonl  17 Phase-2 records (target=null, parked)
data/diva_responses/<sut>__<tier>.jsonl          DivaResponse fetch artefacts — one file per (SUT × tier);
                                                 replayed by the diva_playback solver
scripts/diva_fetch.py                            Streaming DIVA fetcher — SAIA gateway + Arcana RAG, async,
                                                 idempotent JSONL writes, configurable concurrency
scripts/_run_diva.py                             DIVA matrix orchestrator (2 SUTs × 4 RAG tiers): fetch then eval
scripts/_copilot_proxy.py                        Local OpenAI-compatible proxy for the Copilot grader path
```

## Quickstart

```bash
pip install -r requirements.txt
cp .env.example .env  # fill in keys; OPENAI_API_KEY is enough for the line below

inspect eval inspect_benchmark.py --model openai/gpt-4o-mini --limit 1
inspect view
```

`--limit 1` runs one Phase-1 question for a smoke check. Drop the flag to
evaluate all 18.

## DIVA-specific path

DIVA101 is hosted on KISSKI/GWDG (`openai-api/gwdg/<model>`) with Arcana RAG
over four document tiers (Öff. Mat. → + Gew. Mat. → + b+Bund Mat. → + all DIVA
documents). The matrix uses the GitHub Copilot API as its grader path, fronted
by a local proxy that handles Copilot's OAuth → bearer flow and IDE headers.

**Two-phase pipeline.** The DIVA SUT call cannot run inside Inspect-AI's
generate path: SAIA gateway invocation requires `inference-service:
saia-openai-gateway` header + `stream: true` (Arcana retrieval routinely takes
30–60s, exceeding the gateway's non-streaming timeout), and Inspect-AI's
`OpenAICompatibleAPI` cannot enable HTTP streaming via vendor `extra_body`
(the SDK hard-casts the response to `ChatCompletion`). So the matrix is
decoupled into:

1. **Fetch** (`scripts/diva_fetch.py`) — streams DIVA responses with
   the SAIA header + Arcana ID + DIVA101 system prompt; writes one JSONL
   row per (SUT × tier × question). Bounded concurrency, retry on transient
   failures, idempotent (skip-by-question_id), with `[RREF…]` retrieval
   markers extracted via regex.
2. **Score** (`inspect_benchmark.py:diva_playback` solver) — reads the JSONL
   and replays each row's `raw_response` as the model output for the
   LLM-judge to grade. No SUT call happens during the eval phase.

The orchestrator (`scripts/_run_diva.py`) chains both phases per (SUT × tier).

```bash
# Terminal 1: start the Copilot proxy (reads COPILOT_OAUTH from .env)
python scripts/_copilot_proxy.py

# Terminal 2: run the 2 SUTs × 4 RAGs × 18 questions matrix
python scripts/_run_diva.py
# Speed knob: --concurrency N (default 4). N=6 is safe; the GWDG SAIA
# gateway tolerates ~9 concurrent streams per API key before silent drops.
python scripts/_run_diva.py --concurrency 6

# Other useful flags:
python scripts/_run_diva.py --models qwen3.5 --rags Öff   # filter
python scripts/_run_diva.py --skip-fetch                  # eval-only on existing JSONLs
python scripts/_run_diva.py --only-fetch                  # populate JSONLs, skip judge
python scripts/_run_diva.py --limit 1                     # smoke-test one question per cell
```

**T4 = logical union.** The fourth Arcana tier (`+ all DIVA documents`) uses
the SAIA gateway's undocumented multi-arcana extension — comma-separated IDs
in the `arcana.id` field invoke each Arcana in sequence. The canonical
"All+Documents" arcana on `ananyapam.de01` does not resolve, so T4 is wired
as `…/Betriebsverfassungsgesetz,…/Public+Veridbb,…/Public+Bund` (verified to
retrieve from all three corpora simultaneously, 6 `arcana.event` frames per
call). Swap to the canonical ID if/when it surfaces.

**Resumability.** Every fetch failure persists as an `error`-tagged row in
the JSONL. A re-run of the orchestrator skips successful rows and retries
only the errored ones. The GWDG/SAIA gateway has flaky moments under
sustained load (occasional `APIConnectionError`, `ReadTimeout`, or silent
empty-stream); the fetcher's inline retry handles the cheap transients
(APIConnectionError + silent-EMPTY); ReadTimeouts cost 600s each so they
rely on the orchestrator-level rerun rather than inline retry.

**SKU gate.** Default grader is `gpt-5-mini`. The `free_educational_quota`
Copilot SKU blocks `claude-sonnet-*`, `claude-opus-*`, and `gpt-5.2`/`5.4`
from `/chat/completions`, so `gpt-5-mini` is the strongest 5.x-class model
on the unmetered free pool. If you have `ANTHROPIC_API_KEY` set, edit
`GRADER` near the top of `scripts/_run_diva.py` to
`anthropic/claude-sonnet-4-5` and the proxy is unnecessary.

## Status / scope

- Phase-1 corpus (18 Q): full matrix evaluated post-FIX (see *Results*).
- Phase-2 corpus (17 Q): parked at `data/legal_qa/questions_pending_reference.jsonl` until expert references are commissioned (GEN milestone — AI-augmented; UNION milestone — union-network commissioned).
- IRR validation: protocol design at `docs/irr-protocol.md`; sample materials at `data/irr/` (currently calibrated against the pre-FIX confounded matrix — pending regeneration). Expert raters TBD.

## Results

Full DIVA matrix run 2026-05-04 (post-FIX milestone — see *Methodology
disclosure* below): judge prompt v2 + `gpt-5-mini` grader, 2 SUTs × 4
Arcana RAG configurations × 18 Phase-1 questions = **144 graded samples**.

**Per-cell verdict counts:**

| SUT × Tier                          | worse | on_par | better | verdict mean (0–2) | correct % |
|-------------------------------------|------:|-------:|-------:|-------------------:|----------:|
| `qwen3.5-397b-a17b` × Öff. Mat.     |     8 |      1 |      9 |              1.056 |     55.6% |
| `qwen3.5-397b-a17b` × + Gew. Mat.   |     6 |      2 |     10 |              1.222 |     66.7% |
| `qwen3.5-397b-a17b` × + b+Bund Mat. |     4 |      4 |     10 |              1.333 |     77.8% |
| `qwen3.5-397b-a17b` × + all DIVA    |     4 |      0 |     14 |          **1.556** |     77.8% |
| `openai-gpt-oss-120b` × Öff. Mat.   |     7 |      2 |      9 |              1.111 |     61.1% |
| `openai-gpt-oss-120b` × + Gew. Mat. |     3 |      7 |      8 |              1.278 | **83.3%** |
| `openai-gpt-oss-120b` × + b+Bund    |     6 |      0 |     12 |              1.333 |     66.7% |
| `openai-gpt-oss-120b` × + all DIVA  |     4 |      3 |     11 |              1.389 |     77.8% |

**Verdict mean across 144 samples:** 1.286. **Aggregate correct rate:** 73.6%.

**Findings:**
- **`qwen3.5-397b-a17b` shows strict monotonic tier elevation** in both metrics (1.06 → 1.22 → 1.33 → 1.56 in verdict mean; 56% → 67% → 78% → 78% in correct rate). Adding retrieval breadth reliably improves answer quality.
- **`openai-gpt-oss-120b` is non-monotonic in correct%**: peaks at T2 (83.3%), dips at T3 (66.7%), recovers at T4 (77.8%). Verdict mean still climbs (1.11 → 1.28 → 1.33 → 1.39), but the T2→T3 transition flips 3 hits back to misses. Adding b+Bund material *hurt* gpt-oss on a subset of questions.
- **gpt-oss × T2 (Gew. Mat.) is the matrix's strongest single cell** — 83.3% correct, 7 on_par + 8 better. Training material moves gpt-oss the most in absolute terms.
- **Both SUTs converge at the T4 logical union (77.8% correct)**, but `qwen3.5-397b-a17b` leverages broad retrieval into `better_than_reference` more often (mean 1.556 vs gpt-oss's 1.389). qwen3.5 T4 has 14 `better` and 0 `on_par` (highly polarized toward exceeding the reference).
- **RAG depth materially moves quality** — contradicting the pre-FIX matrix's reading. The pre-FIX matrix was actually measuring raw vLLM with no RAG (see *Methodology disclosure*); the cross-tier deltas there were batch-inference noise across no-op parameter values.

**Caveat:** these verdicts are LLM-judge verdicts only; **inter-rater
reliability against human experts is not yet validated**. The IRR sample
at `data/irr/` is the next step. Treat the numbers above as benchmark
signal pending IRR validation, not as final claims.

**Reproducibility.** Per-(SUT × tier) DIVA responses persisted as JSONL at
`data/diva_responses/<sut>__<tier>.jsonl`; replay any row through the judge
with `python scripts/_run_diva.py --skip-fetch`. Per-sample grading `.eval`
logs at `data/logs/2026-05-04T13-*` and `2026-05-04T14-*`. Open with
`inspect view --log-dir data/logs/`.

## Methodology disclosure

The DIVA matrix at commit `8949ea9` (2026-04-29) measured raw vLLM model
output, **not** Arcana-augmented DIVA RAG. The matrix configuration set
`extra_body={"arcana": {"id": ...}}` on the OpenAI-compatible endpoint, but
SAIA gateway routing requires the `inference-service: saia-openai-gateway`
header to actually invoke RAG retrieval. Without that header, the gateway
silently accepts and discards the arcana parameter. The bug was discovered
2026-04-29 via direct httpx probing (an *invalid* arcana ID returned 200
OK without the header but a 500 error with the header — the smoking gun
for silent no-op).

The fix landed 2026-05-04 as a two-phase pipeline (see *DIVA-specific
path*). The full matrix in this README's *Results* section uses
post-FIX data only. The pre-FIX `.eval` logs at `data/logs/2026-04-29T*`
remain in the repo as evidence but should not be cited for cross-tier
conclusions.

## Historical context

The retired 4-axis stance rubric (Solidarity / Collectivism / Rights-awareness
/ Actionability + refusal class, 20 advice scenarios) is preserved at the
`v0.1-axis-pipeline` tag (commit `4723678`):

```bash
git checkout v0.1-axis-pipeline
```

Ten Feb–Mar 2026 evaluation runs against the axis pipeline live under
`data/logs/2026-02-25*` and `data/logs/2026-03-23*`. They are not loaded by
the current task.

## Contact

Arne Tillmann · Dr. Alexander Silbersdorff (primary supervisor)
