"""Run union benchmark against multiple OpenAI models."""
import os, sys, time

os.environ["INSPECT_DISPLAY"] = "none"
os.environ["INSPECT_LOG_LEVEL"] = "warning"

from dotenv import load_dotenv
load_dotenv()

from inspect_ai import eval
from inspect_benchmark import union_benchmark

MODELS = [
    "openai/gpt-5-mini",
    "openai/o3-mini",
    "openai/o4-mini",
    "openai/gpt-4.1-mini",
    "openai/gpt-5.2",
]

task = union_benchmark()

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
