# Legal-QA Output-Quality Benchmark for DIVA

Master's thesis repository — Georg-August-Universität Göttingen.
Primary supervisor: Dr. Alexander Silbersdorff. Aligned with the KIBI/DIVA project (ver.di / Uni Göttingen / TU Clausthal / ver.di b+b).

## TL;DR

Full DIVA matrix run 2026-05-04 — 2 SUTs × 4 RAG tiers × 18 Phase-1 questions = 144 LLM-judged samples:

- **RAG depth lifts answer quality on both SUTs** (verdict mean 1.06 → 1.56 on `qwen3.5-397b-a17b`; 1.11 → 1.39 on `openai-gpt-oss-120b`).
- **`qwen3.5-397b-a17b` is strictly monotonic across tiers; `openai-gpt-oss-120b` is non-monotonic** (peaks at T2, dips at T3, recovers at T4).
- **Aggregate correct rate: 73.6%** — but verdicts are LLM-judge only; inter-rater reliability against human experts is **not yet validated**. Treat as benchmark signal pending IRR.

## What this is

This thesis builds a reusable benchmark for legal-QA quality on German labor-law
questions from union advice practice, then applies it to compare frontier
commercial LLMs against DIVA (a RAG-augmented internal assistant for ver.di).

Each System-Under-Test (SUT) is scored against expert reference answers via an
LLM-as-judge protocol that emits a 3-level verdict:

- `worse_than_reference` — misses key reference points, contains legal errors, or hallucinates paragraphs/sources
- `on_par_with_reference` — covers the reference's substantive points, no major errors
- `better_than_reference` — covers the reference plus adds correct, relevant content

A binary `correct` is derived: `1.0` iff the verdict is `on_par` or `better`,
else `0.0`. Per-sample verdict + reasoning land in the `.eval` log alongside
the SUT output for inspection.

Substrate: the Phase-1+2 TESTFRAGEN corpus from DIVA testing (35
expert-authored questions; 18 carry reference answers and are scorable today,
17 are parked until expert references are commissioned).

## Glossary

- **SUT** — System Under Test. The model whose output gets graded.
- **DIVA101** — the legal-QA assistant being benchmarked. Hosted on KISSKI/GWDG, uses Arcana RAG over union/labor-law documents.
- **GWDG / KISSKI** — Göttingen academic compute cluster + its AI service. Provides API access to open-weight models and to the SAIA gateway.
- **SAIA gateway** — GWDG's OpenAI-compatible front-end. Triggers RAG retrieval when invoked with the right header.
- **Arcana** — GWDG's RAG framework. Each Arcana ID points at one document corpus.
- **RAG tier** — which corpora the SUT can retrieve from. T1 = public material only; T4 = all DIVA documents (logical union).
- **Grader / judge** — the LLM that compares SUT output to the expert reference and emits a verdict. `gpt-5-mini` by default.
- **IRR** — Inter-Rater Reliability. Validation step against human experts; not yet run.
- **Inspect AI** — UK AISI's eval framework. Provides the `task` / `solver` / `scorer` abstractions used here.

## File layout

**Entry points** — these are what you actually run.

```
scripts/_run_diva.py          ▶ DIVA matrix orchestrator. Chains fetch → score per
                                (SUT × RAG tier). Underscore prefix = runner script,
                                not a library import.
inspect_benchmark.py          ▶ Inspect-AI task definition. Run with `inspect eval`
                                for the frontier-path smoke check; also hosts the
                                `diva_playback` solver that _run_diva.py drives.
scripts/_copilot_proxy.py     ▶ Local HTTP proxy that fronts GitHub Copilot's chat
                                API as if it were OpenAI. Needed only when the
                                grader is a Copilot model.
```

**Data.**

```
data/legal_qa/questions_with_reference.jsonl     18 Phase-1 records (scorable today).
data/legal_qa/questions_pending_reference.jsonl  17 Phase-2 records (parked — no target yet).
data/diva_responses/<sut>__<tier>.jsonl          DIVA fetch cache; one file per matrix cell.
data/logs/                                       Inspect-AI `.eval` logs. See README inside
                                                 for what's citable vs retired.
```

**Library code** (imported, not run directly).

```
schema.py              Pydantic data models — Question, Verdict, ModelEvaluation, DivaResponse.
scripts/diva_fetch.py  Streaming SAIA + Arcana fetcher used by _run_diva.py.
judge_prompt.txt       German 3-level LLM-judge prompt.
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

**Prerequisites.**

- **`GWDG_API_KEY`** — academic compute access via KISSKI/GWDG. Apply at
  https://docs.hpc.gwdg.de/services/ai-services/saia/index.html#api-request
  (uni mail required; approval typically same-week). Set `GWDG_API_KEY` and
  `GWDG_BASE_URL` in `.env`.
- **`COPILOT_OAUTH`** — only needed for the Copilot grader path. Free with
  the GitHub Student Developer Pack: apply at https://education.github.com/pack
  (uni mail), activate Copilot in your GitHub settings, then extract the
  `oauth_token` from your local Copilot install (`~/.config/github-copilot/`
  on Linux, `~/Library/Application Support/github-copilot/` on macOS — the
  `apps.json` or `hosts.json` file). Set `COPILOT_OAUTH=ghu_...` in `.env`.
- **Skip the proxy** by setting `ANTHROPIC_API_KEY` instead and editing
  `GRADER` near the top of `scripts/_run_diva.py` to
  `anthropic/claude-sonnet-4-5`.

DIVA101 is hosted on KISSKI/GWDG (`openai-api/gwdg/<model>`) with Arcana RAG
over four document tiers (Öff. Mat. → + Gew. Mat. → + b+Bund Mat. → + all DIVA
documents). The matrix uses the GitHub Copilot API as its grader path.

**Two-phase pipeline.** Inspect-AI's generate path can't host the DIVA SUT
call (Arcana retrieval needs streaming, which `OpenAICompatibleAPI` won't
pass through; see [^fix] for the bug-hunt). So the matrix is decoupled:

1. **Fetch** (`scripts/diva_fetch.py`) — streams DIVA responses with
   the SAIA header + Arcana ID + DIVA101 system prompt; writes one JSONL
   row per (SUT × tier × question). Bounded concurrency, retry on transient
   failures, idempotent (skip-by-question_id), with `[RREF…]` retrieval
   markers extracted via regex.
2. **Score** (`inspect_benchmark.py:diva_playback` solver) — reads the JSONL
   and replays each row's `raw_response` as the model output for the
   LLM-judge to grade. No SUT call happens during the eval phase.

The orchestrator (`scripts/_run_diva.py`) chains both phases per (SUT × tier).

**Copilot proxy.** Copilot's chat-completions endpoint speaks OpenAI's wire
format but adds two things Inspect-AI's `openai-api` provider can't handle:
(a) a 2-step OAuth → 30-min bearer flow, and (b) mandatory streaming with
custom IDE headers. `scripts/_copilot_proxy.py` runs locally on `:8765`,
mints and refreshes the bearer, attaches the IDE headers, and collapses
upstream SSE back to a non-streamed JSON dict if Inspect asked for one.
Inspect sees a plain OpenAI-compatible service.

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

After a run completes, browse the per-sample verdicts:

```bash
inspect view --log-dir data/logs/
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

**Why `gpt-5-mini` is the default grader.** The free Copilot tier
(`free_educational_quota`, what you get with the Student Pack) blocks
`claude-sonnet-*`, `claude-opus-*`, and `gpt-5.2` / `5.4` from
`/chat/completions`. `gpt-5-mini` is the strongest 5.x-class model the free
pool will actually serve, so it's the default. Swap to Claude via the
Anthropic-fallback bullet at the top of this section if you have the key.

## Status / scope

- Phase-1 corpus (18 Q): full matrix evaluated post-FIX (see *Results*).
- Phase-2 corpus (17 Q): parked at `data/legal_qa/questions_pending_reference.jsonl` until expert reference answers are commissioned. Two paths under consideration:
  - **GEN milestone** — AI-drafted references reviewed and corrected by experts.
  - **UNION milestone** — references written from scratch via the ver.di expert network.
- IRR validation: protocol design at `docs/irr-protocol.md`; sample materials at `data/irr/` (currently calibrated against the pre-FIX confounded matrix — pending regeneration). Expert raters TBD.

## Results

Full DIVA matrix run 2026-05-04 (post-FIX milestone[^fix]): judge
prompt v2 + `gpt-5-mini` grader, 2 SUTs × 4 Arcana RAG configurations
× 18 Phase-1 questions = **144 graded samples**.

**Per-cell verdict counts:**

| Tier × SUT                                | worse | on_par | better | verdict mean (0–2) | correct % |
|-------------------------------------------|------:|-------:|-------:|-------------------:|----------:|
| Öff. Mat. × `qwen3.5-397b-a17b`           |     8 |      1 |      9 |              1.056 |     55.6% |
| Öff. Mat. × `openai-gpt-oss-120b`         |     7 |      2 |      9 |              1.111 |     61.1% |
| + Gew. Mat. × `qwen3.5-397b-a17b`         |     6 |      2 |     10 |              1.222 |     66.7% |
| + Gew. Mat. × `openai-gpt-oss-120b`       |     3 |      7 |      8 |              1.278 | **83.3%** |
| + b+Bund Mat. × `qwen3.5-397b-a17b`       |     4 |      4 |     10 |              1.333 |     77.8% |
| + b+Bund Mat. × `openai-gpt-oss-120b`     |     6 |      0 |     12 |              1.333 |     66.7% |
| + all DIVA × `qwen3.5-397b-a17b`          |     4 |      0 |     14 |          **1.556** |     77.8% |
| + all DIVA × `openai-gpt-oss-120b`        |     4 |      3 |     11 |              1.389 |     77.8% |

**Verdict mean across 144 samples:** 1.286. **Aggregate correct rate:** 73.6%.

**Findings:**
- **`qwen3.5-397b-a17b` shows strict monotonic tier elevation** in both metrics (1.06 → 1.22 → 1.33 → 1.56 in verdict mean; 56% → 67% → 78% → 78% in correct rate). Adding retrieval breadth reliably improves answer quality.
- **`openai-gpt-oss-120b` is non-monotonic in correct%**: peaks at T2 (83.3%), dips at T3 (66.7%), recovers at T4 (77.8%). Verdict mean still climbs (1.11 → 1.28 → 1.33 → 1.39), but the T2→T3 transition flips 3 hits back to misses. Adding b+Bund material *hurt* gpt-oss on a subset of questions.
- **gpt-oss × T2 (Gew. Mat.) is the matrix's strongest single cell** — 83.3% correct, 7 on_par + 8 better. Training material moves gpt-oss the most in absolute terms.
- **Both SUTs converge at the T4 logical union (77.8% correct)**, but `qwen3.5-397b-a17b` leverages broad retrieval into `better_than_reference` more often (mean 1.556 vs gpt-oss's 1.389). qwen3.5 T4 has 14 `better` and 0 `on_par` (highly polarized toward exceeding the reference).
- **RAG depth materially moves quality** — contradicting the pre-FIX matrix's reading[^fix].

**Caveat:** these verdicts are LLM-judge verdicts only; **inter-rater
reliability against human experts is not yet validated**. The IRR sample
at `data/irr/` is the next step. Treat the numbers above as benchmark
signal pending IRR validation, not as final claims.

**Reproducibility.** Per-(SUT × tier) DIVA responses persisted as JSONL at
`data/diva_responses/<sut>__<tier>.jsonl`; replay any row through the judge
with `python scripts/_run_diva.py --skip-fetch`. Per-sample grading `.eval`
logs at `data/logs/2026-05-04T20-*` (qwen3.5) and `data/logs/2026-05-05T08-*`
(gpt-oss); see `data/logs/README.md` for what's citable. Open with
`inspect view --log-dir data/logs/`.

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

Arne Tillmann (a.tillmann@stud.uni-goettingen.de) · Dr. Alexander Silbersdorff (primary supervisor)

---

[^fix]: **Methodology disclosure.** The DIVA matrix at commit `8949ea9` (2026-04-29) measured raw vLLM model output, *not* Arcana-augmented DIVA RAG. The matrix configuration set `extra_body={"arcana": {"id": ...}}` on the OpenAI-compatible endpoint, but SAIA gateway routing requires the `inference-service: saia-openai-gateway` header to actually invoke RAG retrieval — without that header, the gateway silently accepts and discards the arcana parameter. The bug ran undetected for ~2 weeks (2026-04-15 → 2026-05-04) and was discovered via direct httpx probing (an *invalid* arcana ID returned 200 OK without the header but a 500 error with it — the smoking gun for silent no-op). The fix landed 2026-05-04 as a two-phase pipeline (see *DIVA-specific path*). All cross-tier results above use post-FIX data only. Pre-FIX `.eval` logs at `data/logs/2026-04-29T*` remain in the repo as evidence — see `data/logs/README.md` for the per-run inventory and what each log can/cannot be cited for — but should not be cited for cross-tier conclusions.
