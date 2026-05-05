"""Run the DIVA101 evaluation matrix: 2 backbone models × 4 Arcana RAG configs.

DIVA101 is the legal-knowledge-finder persona of the KIBI/DIVA system. The two
backbone models are paired with four Arcana RAG knowledge bases that scale the
document corpus from public material only ("Öff. Mat.") through the full
union/Bund-Verlag library.

Two-phase pipeline (decided 2026-04-29 — see
`Agent-ClaudeCode/diagnostics/2026-04-29_arcana-finding-followup.md` §1c):

  1. **Fetch** — `scripts/diva_fetch.py` streams DIVA101 responses with the
     SAIA gateway header + Arcana RAG; one JSONL per (SUT × tier).
  2. **Score** — Inspect-AI replays each JSONL via the `diva_playback` solver
     and routes the response through the judge. No SUT call happens during
     the eval.

Streaming is required because Arcana retrieval + qwen reasoning preamble takes
30–50s and non-streaming requests die at the gateway's ~10s ReadTimeout.
Inspect-AI's `OpenAICompatibleAPI` cannot stream via `extra_body`
(`openai_compatible.py:290` hard-casts to `ChatCompletion`), hence the decouple.

Grader: openai-api/copilot/gpt-5-mini (frontier, not the SUT — no self-grading).

Usage:
    python scripts/_run_diva.py                       # full 8-config × 18-Q matrix
    python scripts/_run_diva.py --limit 1             # smoke: one Q per config
    python scripts/_run_diva.py --models qwen3        # substring-filter SUTs
    python scripts/_run_diva.py --rags "Öff"          # substring-filter RAGs
    python scripts/_run_diva.py --skip-fetch          # reuse existing JSONLs

Env (.env):
    GWDG_API_KEY, GWDG_BASE_URL    — DIVA backbone access
    OPENAI_API_KEY                 — copilot proxy / grader
    INSPECT_LOG_DIR                — defaults to data/logs/
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

# Quiet by default; pass `INSPECT_DISPLAY=full` to see live progress.
os.environ.setdefault("INSPECT_DISPLAY", "none")
os.environ.setdefault("INSPECT_LOG_LEVEL", "warning")

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")

from inspect_ai import eval

from inspect_benchmark import legal_qa_benchmark, QUESTIONS_PATH
from diva_fetch import fetch_run, resolve_out_path, _load_questions


# ── DIVA101 configuration ────────────────────────────────────────────────────

DIVA_MODELS = [
    # qwen3-235b-a22b retired from GWDG; qwen3.5-397b-a17b is the current heir
    # (largest, newest Qwen on the catalog as of 2026-04-28). Verified Arcana-
    # compatible with streaming (~50s warm vs ~29s for qwen3-30b-a3b).
    "openai-api/gwdg/qwen3.5-397b-a17b",
    "openai-api/gwdg/openai-gpt-oss-120b",
]

# Arcana RAG knowledge bases (public → full library).
#
# T4 is a *logical* union of T1+T2+T3 via the SAIA gateway's comma-separated
# multi-arcana extension (probed 2026-05-04). The canonical "All+Documents"
# arcana on ananyapam.de01 doesn't resolve — every variant tried returns
# 500 "Error reading arcana ... Check your arcana ID." Until the canonical
# T4 surfaces (whoever curates ananyapam.de01's Arcanas), the logical-union
# form below retrieves cleanly from all three corpora simultaneously, with
# 6 arcana.event frames per call and RREFs spanning BetrVG.pdf + ver.di b+b
# training materials + Bund-Verlag practitioner docs.
#
# Document populations are NOT strictly cumulative across the pre-built
# composites — verified by smoke 3 RREFs: T2 retrieves no BetrVG.pdf despite
# the "Public+" prefix, and T3 only partially overlaps T1. The 3-way comma
# string is the empirically-correct way to cover all three corpora.
RAG_CONFIGS: list[tuple[str, str]] = [
    ("Öff. Mat.",            "ananyapam.de01/Betriebsverfassungsgesetz"),
    ("+ Gew. Mat.",          "ananyapam.de01/Public+Veridbb"),
    ("+ b+Bund Mat.",        "ananyapam.de01/Public+Bund"),
    ("+ all DIVA documents", "ananyapam.de01/Betriebsverfassungsgesetz,"
                             "ananyapam.de01/Public+Veridbb,"
                             "ananyapam.de01/Public+Bund"),
]

GRADER = "openai-api/copilot/gpt-5-mini"

# Inspect-AI requires a model arg even when `generate()` is never called.
# `mockllm` has no API and never fails on connect; the actual SUT identity
# lives in each DivaResponse JSONL row (`sut_model` field).
PLAYBACK_MODEL = "mockllm/diva-playback"


# ── Runner ──────────────────────────────────────────────────────────────────

def _print_header(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(title)
    print('=' * 60)


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
    parser.add_argument("--skip-fetch", action="store_true",
                        help="Skip the fetch phase; reuse existing JSONLs at "
                             "data/diva_responses/. Errors out if any JSONL is missing.")
    parser.add_argument("--only-fetch", action="store_true",
                        help="Run only the fetch phase; skip the eval/judge.")
    parser.add_argument("--concurrency", type=int, default=4,
                        help="Max concurrent in-flight fetches per (SUT × tier). "
                             "Default 4. Set to 1 for fully sequential.")
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
    print(f"Phases:      "
          f"{'fetch only' if args.only_fetch else ('eval only (--skip-fetch)' if args.skip_fetch else 'fetch + eval')}")

    questions = _load_questions(QUESTIONS_PATH, ids=None, limit=args.limit)
    print(f"Questions:   {len(questions)} (phase-1 with reference)")

    failed: list[tuple[str, str, str, str]] = []  # (model, rag, phase, error)

    for model in models:
        for rag_label, arcana_id in rags:
            _print_header(f"SUT:  {model}\nRAG:  {rag_label}  ({arcana_id})")

            out_path = resolve_out_path(None, model, rag_label)

            # ── Phase 1 — fetch ──
            if not args.skip_fetch:
                try:
                    print(f"[fetch] → {out_path.relative_to(REPO_ROOT)}")
                    t0 = time.monotonic()
                    n_attempted, n_ok, n_err = asyncio.run(
                        fetch_run(model, arcana_id, rag_label, out_path, questions,
                                  concurrency=args.concurrency)
                    )
                    elapsed = time.monotonic() - t0
                    print(f"[fetch] {n_ok}/{n_attempted} ok, {n_err} errored ({elapsed:.1f}s)")
                    if n_err:
                        failed.append((model, rag_label, "fetch",
                                       f"{n_err} of {n_attempted} questions failed"))
                        continue  # don't grade an incomplete fetch
                except Exception as e:
                    print(f"[fetch] EXCEPTION: {e}")
                    failed.append((model, rag_label, "fetch", str(e)))
                    continue

            elif not out_path.exists():
                msg = f"--skip-fetch set but {out_path} does not exist"
                print(f"[fetch] SKIP+MISSING: {msg}")
                failed.append((model, rag_label, "fetch", msg))
                continue

            if args.only_fetch:
                continue

            # ── Phase 2 — eval (judge only) ──
            print(f"[eval] playback={out_path.relative_to(REPO_ROOT)}")
            t0 = time.monotonic()
            try:
                eval_kwargs = dict(
                    model=PLAYBACK_MODEL,
                    model_roles={"grader": args.grader},
                )
                if args.limit is not None:
                    eval_kwargs["limit"] = args.limit
                task = legal_qa_benchmark(playback_jsonl=str(out_path))
                result = eval(task, **eval_kwargs)[0]
                elapsed = time.monotonic() - t0
                print(f"[eval] status: {result.status}  ({elapsed:.1f}s)")
                if result.status != "success":
                    err_msg = (getattr(result, "error", None)
                               and (result.error.message or "unknown")) or "non-success status"
                    failed.append((model, rag_label, "eval",
                                   f"status={result.status}: {err_msg}"))
                if result.results:
                    print(f"[eval] samples: {result.results.completed_samples}/"
                          f"{result.results.total_samples}")
                    for score_entry in result.results.scores or []:
                        for mk, mv in score_entry.metrics.items():
                            print(f"       {score_entry.name}/{mk}: {mv.value:.3f}")
            except Exception as e:
                elapsed = time.monotonic() - t0
                print(f"[eval] ERROR after {elapsed:.1f}s: {e}")
                failed.append((model, rag_label, "eval", str(e)))

    print(f"\n{'=' * 60}")
    n_eval_failed = len([f for f in failed if f[2] == "eval"])
    n_attempted_eval = n_runs - len([f for f in failed if f[2] == "fetch"])
    print(f"Done. {n_attempted_eval - n_eval_failed}/{n_runs} eval runs succeeded.")
    if failed:
        print(f"\nFailures:")
        for m, r, phase, e in failed:
            print(f"  - [{phase}] {m} × {r}: {e[:200]}")
    print(f"\nView results: inspect view --log-dir {os.environ.get('INSPECT_LOG_DIR', 'logs/')}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
