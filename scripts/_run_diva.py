"""Run the DIVA101 evaluation matrix: 2 backbone models × 4 Arcana RAG configs.

DIVA101 is the legal-knowledge-finder persona of the KIBI/DIVA system. The two
backbone models are paired with four Arcana RAG knowledge bases that scale the
document corpus from public material only ("Öff. Mat.") through the full
union/Bund-Verlag library.

Grader: anthropic/claude-sonnet-4-5 (frontier, not the SUT — no self-grading).

Usage:
    python scripts/_run_diva.py                       # full 8-config × 18-Q matrix
    python scripts/_run_diva.py --limit 1             # smoke: one Q per config
    python scripts/_run_diva.py --models qwen3        # substring-filter SUTs
    python scripts/_run_diva.py --rags "Öff"          # substring-filter RAGs

Env (.env):
    GWDG_API_KEY, GWDG_BASE_URL    — DIVA backbone access
    ANTHROPIC_API_KEY              — Claude grader
    INSPECT_LOG_DIR                — defaults to data/logs/
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# Quiet by default; pass `INSPECT_DISPLAY=full` to see live progress.
os.environ.setdefault("INSPECT_DISPLAY", "none")
os.environ.setdefault("INSPECT_LOG_LEVEL", "warning")

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")

from inspect_ai import eval
from inspect_ai.model import GenerateConfig

from inspect_benchmark import SUT_DECODING, legal_qa_benchmark


# ── DIVA101 configuration ────────────────────────────────────────────────────

# Backbone models hosted on KISSKI/GWDG.
DIVA_MODELS = [
    # qwen3-235b-a22b retired from GWDG; qwen3.5-397b-a17b is the current heir
    # (largest, newest Qwen on the catalog as of 2026-04-28).
    "openai-api/gwdg/qwen3.5-397b-a17b",
    "openai-api/gwdg/openai-gpt-oss-120b",
]

# Arcana RAG knowledge bases (public → full library).
RAG_CONFIGS: list[tuple[str, str]] = [
    ("Öff. Mat.",            "ananyapam.de01/Betriebsverfassungsgesetz"),
    ("+ Gew. Mat.",          "ananyapam.de01/Public+Veridbb"),
    ("+ b+Bund Mat.",        "ananyapam.de01/Public+Bund"),
    ("+ all DIVA documents", "ananyapam.de01/All+Documents"),
]

GRADER = "openai-api/copilot/claude-haiku-4.5"


# ── Runner ──────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--limit", type=int, default=None,
                        help="Sample limit per run (default: all 18 Phase-1 questions)")
    parser.add_argument("--models", default=None,
                        help="Substring filter on SUT model names (e.g. 'qwen3')")
    parser.add_argument("--rags", default=None,
                        help="Substring filter on RAG labels (e.g. 'Öff')")
    parser.add_argument("--grader", default=GRADER,
                        help=f"Grader model (default: {GRADER})")
    args = parser.parse_args()

    models = [m for m in DIVA_MODELS if args.models is None or args.models in m]
    rags = [(label, aid) for label, aid in RAG_CONFIGS
            if args.rags is None or args.rags in label]

    if not models or not rags:
        print("ERROR: filter excluded all configs.", file=sys.stderr)
        return 2

    n_runs = len(models) * len(rags)
    print(f"DIVA matrix: {len(models)} models × {len(rags)} RAGs = {n_runs} runs")
    print(f"Grader:      {args.grader}")
    print(f"Sample limit per run: {args.limit if args.limit is not None else 'all (18)'}")
    print(f"Log dir:     {os.environ.get('INSPECT_LOG_DIR', './logs/')}")
    print()

    failed: list[tuple[str, str, str]] = []

    for model in models:
        for rag_label, arcana_id in rags:
            print(f"\n{'=' * 60}")
            print(f"SUT:  {model}")
            print(f"RAG:  {rag_label}  ({arcana_id})")
            print(f"{'=' * 60}")

            task = legal_qa_benchmark()
            task.config = GenerateConfig(
                temperature=SUT_DECODING.temperature,
                top_p=SUT_DECODING.top_p,
                extra_body={"arcana": {"id": arcana_id}},
            )

            t0 = time.time()
            try:
                eval_kwargs = dict(
                    model=model,
                    model_roles={"grader": args.grader},
                )
                if args.limit is not None:
                    eval_kwargs["limit"] = args.limit
                result = eval(task, **eval_kwargs)[0]
                elapsed = time.time() - t0
                print(f"  Status:  {result.status}")
                if result.results:
                    print(f"  Samples: {result.results.completed_samples}/"
                          f"{result.results.total_samples}")
                    for score_entry in result.results.scores or []:
                        for mk, mv in score_entry.metrics.items():
                            print(f"    {score_entry.name}/{mk}: {mv.value:.3f}")
                print(f"  Time:    {elapsed:.1f}s")
            except Exception as e:
                elapsed = time.time() - t0
                print(f"  ERROR after {elapsed:.1f}s: {e}")
                failed.append((model, rag_label, str(e)))

    print(f"\n{'=' * 60}")
    print(f"Done. {n_runs - len(failed)}/{n_runs} runs succeeded.")
    if failed:
        print(f"\nFailures:")
        for m, r, e in failed:
            print(f"  - {m} × {r}: {e[:200]}")
    print(f"\nView results: inspect view --log-dir {os.environ.get('INSPECT_LOG_DIR', 'logs/')}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
