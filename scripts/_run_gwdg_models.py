"""Run union benchmark against all GWDG Chat AI models (with Arcana RAG).

Uses Inspect AI's built-in openai-api provider with the GWDG service prefix.
Models are invoked as  openai-api/gwdg/<model-id>  which auto-resolves
GWDG_API_KEY and GWDG_BASE_URL from .env.

The Arcana RAG knowledge base (Betriebsverfassungsgesetz) is injected into
every request via GenerateConfig.extra_body.
"""

import os
import sys
import time
from pathlib import Path

os.environ["INSPECT_DISPLAY"] = "none"
os.environ["INSPECT_LOG_LEVEL"] = "warning"

# Make the project root importable so `from inspect_benchmark import ...` resolves
# when this script is run as `python scripts/_run_gwdg_models.py`.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")

from inspect_ai import eval
from inspect_ai.model import GenerateConfig

from inspect_benchmark import legal_qa_benchmark

# ── Arcana RAG config ────────────────────────────────────────────────────────

ARCANA_ID = os.environ.get(
    "GWDG_ARCANA_ID", "ananyapam.de01/Betriebsverfassungsgesetz"
)

ARCANA_EXTRA_BODY = {
    "arcana": {"id": ARCANA_ID},
}

# ── GWDG models (from /v1/models endpoint, 2026-03-23) ──────────────────────
# Text-only and text+image models suitable for the benchmark.
# Skipped: vision/audio-only (InternVL, Qwen VL/Omni), medical (MedGemma).

MODELS = [
    # --- Small / fast (good for testing) ---
    "openai-api/gwdg/meta-llama-3.1-8b-instruct",
    "openai-api/gwdg/teuken-7b-instruct-research",
    # --- Medium ---
    "openai-api/gwdg/gemma-3-27b-it",
    "openai-api/gwdg/qwen3-coder-30b-a3b-instruct",
    "openai-api/gwdg/qwen3-30b-a3b-instruct-2507",
    "openai-api/gwdg/qwen3-32b",
    "openai-api/gwdg/qwen3-30b-a3b-thinking-2507",
    # --- Large ---
    "openai-api/gwdg/llama-3.3-70b-instruct",
    "openai-api/gwdg/llama-3.1-sauerkrautlm-70b-instruct",
    "openai-api/gwdg/deepseek-r1-distill-llama-70b",
    "openai-api/gwdg/apertus-70b-instruct-2509",
    # --- XL ---
    "openai-api/gwdg/openai-gpt-oss-120b",
    "openai-api/gwdg/devstral-2-123b-instruct-2512",
    "openai-api/gwdg/qwen3-235b-a22b",
    "openai-api/gwdg/glm-4.7",
    "openai-api/gwdg/mistral-large-3-675b-instruct-2512",
]

# ── Run ──────────────────────────────────────────────────────────────────────

task = legal_qa_benchmark()
task.config = GenerateConfig(extra_body=ARCANA_EXTRA_BODY)

for model in MODELS:
    print(f"\n{'='*60}")
    print(f"Running: {model}")
    print(f"{'='*60}")
    t0 = time.time()
    try:
        result = eval(task, model=model)[0]
        elapsed = time.time() - t0
        print(f"  Status:  {result.status}")
        print(f"  Samples: {result.results.completed_samples}/{result.results.total_samples}")
        print(f"  Time:    {elapsed:.1f}s")
        if result.results and result.results.scores:
            for score_entry in result.results.scores:
                print(f"  Scorer:  {score_entry.name}")
                for mk, mv in score_entry.metrics.items():
                    print(f"    {mk}: {mv.value:.3f}")
    except Exception as e:
        elapsed = time.time() - t0
        print(f"  ERROR after {elapsed:.1f}s: {e}")

print(f"\n{'='*60}")
print("All done.")
