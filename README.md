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
legal_qa_schema.py                              Pydantic models for the Question records
inspect_benchmark.py                            Inspect AI task — the entry point
judge_prompt.txt                                German LLM-judge prompt (3-level verdict)
data/legal_qa/questions_with_reference.jsonl    18 Phase-1 records (scorable)
data/legal_qa/questions_pending_reference.jsonl 17 Phase-2 records (target=null, parked)
scripts/_run_diva.py                            DIVA matrix runner (2 SUTs × 4 RAGs)
scripts/_copilot_proxy.py                       Local OpenAI-compatible proxy for the Copilot grader path
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
documents). The DIVA matrix uses the GitHub Copilot API as its grader path,
fronted by a local proxy that handles Copilot's OAuth → bearer flow and the
required IDE headers.

```bash
# Terminal 1: start the proxy (reads COPILOT_OAUTH from .env)
python scripts/_copilot_proxy.py

# Terminal 2: run the 2 SUTs × 4 RAGs × 18 questions matrix
python scripts/_run_diva.py
```

**SKU gate.** Default grader is `gpt-5-mini`. The `free_educational_quota`
Copilot SKU blocks `claude-sonnet-*`, `claude-opus-*`, and `gpt-5.2`/`5.4`
from `/chat/completions`, so `gpt-5-mini` is the strongest 5.x-class model
on the unmetered free pool. If you have `ANTHROPIC_API_KEY` set, edit
`GRADER` near the top of `scripts/_run_diva.py` to
`anthropic/claude-sonnet-4-5` and the proxy is unnecessary.

## Status / scope

- Phase-1 corpus (18 Q): scorable today against the LLM-judge.
- Phase-2 corpus (17 Q): parked at `data/legal_qa/questions_pending_reference.jsonl` until expert references are commissioned (GEN milestone — AI-augmented; UNION milestone — union-network commissioned).
- IRR validation: protocol design at `docs/irr-protocol.md`; sample materials at `data/irr/`. Expert raters TBD.

## Results

Pilot DIVA matrix run on 2026-04-29 — judge prompt v2 + `gpt-5-mini`
grader, 2 SUTs × 4 Arcana RAG configurations × 18 Phase-1 questions = 144
graded samples.

**Verdict distribution across the 144 samples:**

| Verdict | Count | Share |
|---|---:|---:|
| `worse_than_reference` | 41 | 28.5% |
| `on_par_with_reference` | 84 | 58.3% |
| `better_than_reference` | 19 | 13.2% |

**Per-SUT roll-up:**

| SUT | verdict mean (0–2 scale) | correct rate (on_par OR better) |
|---|---:|---:|
| `qwen3.5-397b-a17b` | 1.12 | 0.88 |
| `openai-gpt-oss-120b` | 0.57 | 0.56 |

**Per-config matrix (verdict mean):**

|                          | Öff. Mat. | + Gew. Mat. | + b+Bund Mat. | + all DIVA documents |
|--------------------------|----------:|------------:|--------------:|---------------------:|
| `qwen3.5-397b-a17b`      | 1.00      | 1.28        | 1.17          | 1.06                 |
| `openai-gpt-oss-120b`    | 0.56      | 0.56        | 0.67          | 0.50                 |

**Findings:** the 3-level scale distributes across all buckets, so the
benchmark can rank model configurations. `qwen3.5-397b-a17b` is materially
stronger than `openai-gpt-oss-120b` for German labor-law QA across all
four RAG tiers. RAG depth has a small, non-monotonic effect within each
SUT — increasing the document corpus does not reliably move correctness.

**Caveat:** these verdicts are LLM-judge verdicts only; **inter-rater
reliability against human experts is not yet validated**. The IRR sample
at `data/irr/` is the next step. Treat the numbers above as pilot
signal, not as benchmarked claims.

Reproducibility: per-sample `.eval` logs at
`data/logs/2026-04-29T10-*` and `2026-04-29T14-01-49*` (the latter is the
`gpt-oss-120b × + Gew. Mat.` rerun after a Copilot-bearer-expiry fix in
`scripts/_copilot_proxy.py`). Open with `inspect view --log-dir data/logs/`.

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
