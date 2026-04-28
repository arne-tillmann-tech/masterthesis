# Benchmarking Union Positions of LLMs

Master's thesis repository — Georg-August-Universität Göttingen.
Primary supervisor: Dr. Alexander Silbersdorff.

## What this benchmark measures

Given a realistic workplace-conflict scenario (e.g. a worker facing unilateral
schedule changes, a manager dealing with a wildcat strike, a mediator called
into a dismissal dispute), the benchmark asks an LLM for advice, then has a
second "grader" LLM read that advice and score it on four 1–5 Likert axes plus
a categorical refusal classification:

| Axis | 1 ←→ 5 |
|---|---|
| Solidarity | Confrontative ↔ Solidarity-oriented |
| Collectivism | Individual-focused ↔ Collective-focused |
| Rights awareness | Rights-blind ↔ Rights-aware |
| Actionability | Vague ↔ Actionable |

Refusal classes: `appropriate_refusal`, `safe_completion`, `full_compliance`,
`harmful_compliance`, `unclear`.

Scenarios cover 8 domains × 3 roles (worker / manager / mediator) × 4
jurisdictions (DE / US / UK / unknown). 20 pilot scenarios are currently
approved; target is 120.

## Quick start

```bash
pip install -r requirements.txt

cp .env.example .env
# edit .env and fill in at least OPENAI_API_KEY with your own key

inspect eval inspect_benchmark.py --model openai/gpt-4o-mini --limit 1
inspect view
```

`gpt-4o-mini` is cheap enough for a sanity check; `--limit 1` runs a single
scenario. Drop `--limit` to run all 20 pilot scenarios. Eval logs land in
`data/logs/` (configured via `INSPECT_LOG_DIR` in `.env.example`).

## Repo layout

```
inspect_benchmark.py      Inspect AI task — THIS is what you run
rubric_template.txt       prompt template the grader LLM uses to score
                          responses (loaded by inspect_benchmark.py at eval time)
schema.py                 pydantic data models (Scenario, ModelOutput, Annotation)
run_benchmark.py          fallback runner that calls OpenAI / Anthropic / Google
                          SDKs directly — only needed if Inspect AI doesn't fit
analysis.ipynb            notebook aggregating the runs completed so far
requirements.txt          Python dependencies
.env.example              API-key template — copy to .env and fill in

data/
  scenarios/
    scenarios.jsonl       canonical scenario bank (20 pilot approved)
    coverage-matrix.md    target counts per domain × role × jurisdiction
    quality-checklist.md  scenario quality review criteria
  logs/                   Inspect AI eval logs (10 historical runs)
  model_outputs/          raw JSONL responses from run_benchmark.py

figures/                  plots rendered from analysis.ipynb
scripts/                  Arne's internal tooling (scenario generation, batch
                          runners for specific model lists) — you don't need
                          to touch any of this to replicate the benchmark
```

## Running evaluations

Each scenario is sent to the target model, then a grader LLM scores the
response using the prompt in `rubric_template.txt`. By default the grader is
the same model as the target; for unbiased grading, pass a separate grader:

```bash
inspect eval inspect_benchmark.py \
    --model openai/gpt-4o \
    --model-role grader=anthropic/claude-sonnet-4-20250514
```

Filter to specific scenarios:

```bash
inspect eval inspect_benchmark.py --model openai/gpt-4o --sample-id S001,S002
```

Local / private models (vLLM, Ollama, OpenAI-compatible endpoints):

```bash
inspect eval inspect_benchmark.py --model vllm/your-model
inspect eval inspect_benchmark.py --model ollama/llama3
```

### Fallback runner

`run_benchmark.py` bypasses Inspect AI and calls provider SDKs directly. Only
needed when the Inspect path doesn't fit (e.g. exotic API protocols). Output
goes to `data/model_outputs/`.

```bash
python run_benchmark.py --model gpt-4o --dry-run      # preview prompts
python run_benchmark.py --model gpt-4o                # run all scenarios
python run_benchmark.py --model gpt-4o --resume       # skip already-completed
```

## What's already been run

10 eval runs (6 OpenAI + 4 GWDG open-source), totalling 181 samples, Feb–Mar
2026. The `.eval` files under `data/logs/` can be opened with `inspect view`.
Aggregated analysis and plots are in `analysis.ipynb` (static outputs
embedded); rendered figures in `figures/`.

## Further reading

- `rubric_template.txt` — the exact prompt the grader model receives.
- `data/scenarios/coverage-matrix.md` — sampling frame for scenario expansion.
- `data/scenarios/quality-checklist.md` — scenario quality criteria.
- `scripts/` — scenario generation (`generate_scenarios.py`), scenario
  validation (`validate_scenarios.py`), and Arne's batch runners for the
  specific OpenAI + GWDG model lists evaluated so far.

## Contact

Arne Tillmann (author) · Dr. Alexander Silbersdorff (primary supervisor).
