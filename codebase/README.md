# Union-Perspective LLM Benchmark – Codebase

## Structure

```
codebase/
  schema.py               – Pydantic models for Scenario, ModelOutput, Annotation
  validate_scenarios.py   – Validate scenarios.jsonl against schema + print coverage
  run_benchmark.py        – Standalone multi-provider API runner (fallback / private LLMs)
  generate_scenarios.py   – LLM-assisted scenario generation for coverage matrix cells
  inspect_benchmark.py    – Inspect AI evaluation task (primary evaluation method)
  rubric_template.txt     – Grading prompt template for the 4-axis rubric scorer
  requirements.txt        – Python dependencies
  .env.example            – Template for API keys

data/
  scenarios/
    scenarios.jsonl       – Canonical scenario bank (JSONL format)
    coverage-matrix.md    – Target counts per domain × role × jurisdiction
    quality-checklist.md  – Review checklist for scenario quality
  model_outputs/          – Raw LLM responses (one JSONL per model × run)
  annotations/            – Human/AI ratings (future)
```

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Copy and fill in API keys
cp .env.example .env
# Edit .env with your keys

# 3. Validate existing scenarios
python validate_scenarios.py
```

## Running Evaluations with Inspect AI (primary)

The benchmark uses [Inspect AI](https://inspect.aisi.org.uk/) for evaluation.
Each scenario is sent to the target model, then a grader LLM scores the
response on 4 axes (1–5) plus a refusal classification.

```bash
# Run all 20 scenarios against a model
inspect eval inspect_benchmark.py --model openai/gpt-4o

# Use a cheaper model for quick testing
inspect eval inspect_benchmark.py --model openai/gpt-4o-mini

# Use a separate grader model (recommended for unbiased grading)
inspect eval inspect_benchmark.py --model openai/gpt-4o \
    --model-role grader=anthropic/claude-sonnet-4-20250514

# Evaluate specific scenarios only
inspect eval inspect_benchmark.py --model openai/gpt-4o --sample-id S001,S002,S003

# Local / private models (vLLM, Ollama, OpenAI-compatible endpoints)
inspect eval inspect_benchmark.py --model vllm/your-model-name
inspect eval inspect_benchmark.py --model ollama/llama3

# View results in the Inspect viewer
inspect view
```

### Scoring axes

| Axis | Scale | Description |
|------|-------|-------------|
| Solidarity | 1–5 | Confrontative ↔ Solidarity-oriented |
| Collectivism | 1–5 | Individual-focused ↔ Collective-focused |
| Rights Awareness | 1–5 | Rights-blind ↔ Rights-aware |
| Actionability | 1–5 | Vague ↔ Actionable |
| Refusal Class | categorical | appropriate_refusal, safe_completion, full_compliance, harmful_compliance, unclear |

## Running with `run_benchmark.py` (fallback)

For edge cases where Inspect AI is not suitable (e.g., truly proprietary API protocols):

```bash
python run_benchmark.py --model gpt-4o --dry-run      # preview
python run_benchmark.py --model gpt-4o                 # actual API calls
python run_benchmark.py --model gpt-4o --resume        # skip completed
```

## Scenario Generation

```bash
# Preview scenarios for a coverage cell
python generate_scenarios.py --domain organizing --role worker --count 5 --dry-run

# Generate and auto-append to scenarios.jsonl
python generate_scenarios.py --domain organizing --role worker --count 5 --append
```

## Key Commands

| Task | Command |
|------|---------|
| Validate scenarios | `python validate_scenarios.py` |
| Run eval (Inspect) | `inspect eval inspect_benchmark.py --model MODEL` |
| Run eval (specific) | `inspect eval inspect_benchmark.py --model MODEL --sample-id S001,S002` |
| View results | `inspect view` |
| Generate scenarios | `python generate_scenarios.py --domain X --role Y --count N --append` |
| Run benchmark (fallback) | `python run_benchmark.py --model MODEL` |
