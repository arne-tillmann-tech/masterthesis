#!/usr/bin/env python3
"""
Search APEX-Agents and GDPval benchmark datasets for labor-union-relevant tasks.

Requirements:
    pip install huggingface_hub datasets

Usage:
    python search_benchmarks.py

Optional:
    Set HF_TOKEN or HUGGINGFACE_HUB_TOKEN to access gated Hugging Face datasets.
"""

import json
import os
import re
import sys
from pathlib import Path

try:
    from huggingface_hub import hf_hub_download
except ImportError:
    print("Install huggingface_hub first:  pip install huggingface_hub")
    raise

try:
    from datasets import load_dataset
except ImportError:
    print("Install datasets first:  pip install datasets")
    raise


# --- Keywords to search for ---
# Broad set: anything a union official might work on or that touches labor relations
KEYWORDS = [
    # Core union terms
    r"\bunion\b", r"\blabor\b", r"\blabour\b",
    r"collective bargaining", r"\bCBA\b",
    r"grievance", r"arbitration",
    r"bargaining unit", r"shop steward", r"union representative",
    r"strike\b", r"lockout", r"picket",
    r"unfair labor practice", r"NLRB", r"NLRA",
    # Employment / HR adjacent
    r"layoff", r"lay-off", r"severance",
    r"termination", r"wrongful termination",
    r"worker rights", r"workers.? rights",
    r"employee rights", r"employment law",
    r"wage theft", r"minimum wage",
    r"overtime", r"working conditions",
    r"occupational safety", r"OSHA",
    r"whistleblow",
    # Restructuring / workforce
    r"restructur", r"workforce reduction",
    r"redundanc", r"retrenchment",
    r"seniority", r"tenure",
    # Contracts & negotiation
    r"employment (contract|agreement)",
    r"compensation negotiat",
    r"wage negotiat",
    r"pay scale", r"pay grade",
    # Broader
    r"worker represent", r"employee represent",
    r"works council", r"Betriebsrat",
    r"co-?determination", r"Mitbestimmung",
]

COMPILED = [re.compile(kw, re.IGNORECASE) for kw in KEYWORDS]
HF_TOKEN = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_HUB_TOKEN")
EXAMPLES_PATH = Path(__file__).parent.parent / "data" / "scenarios" / "example scenarios" / "examples.md"

CURATED_EXAMPLES = {
    "strong": {
        "https://www.gdpval.dev/b39a5aa7-cd1b-47ad-b249-90afd22f8f21": (
            "Direct collective bargaining agreement compensation analysis."
        ),
        "https://www.gdpval.dev/4520f882-715a-482d-8e87-1cb3cbdfe975": (
            "Direct CBA-driven staffing and compensation workflow for musicians."
        ),
    },
    "slight": {
        "https://www.gdpval.dev/bf68f2ad-eac5-490a-adec-d847eb45bd6f": (
            "Shift scheduling and overtime reduction; labor-adjacent but not explicitly union-focused."
        ),
        "https://www.gdpval.dev/efca245f-c24f-4f75-a9d5-59201330ab7a": (
            "Manufacturing labor capacity and overtime planning; relevant at the edge of labor relations."
        ),
        "https://apex-explorer.ooakdata.com/tasks/task_075c6f8ffb1548508e94e67e4ba04bbb": (
            "Previously saved APEX example; kept as a relevant benchmark reference."
        ),
        "https://apex-explorer.ooakdata.com/tasks/task_3d4d03776d704758bb1bb9931e301b1c": (
            "Explicit union demand and labor cost forecasting, though framed as management consulting."
        ),
    },
}

STRONG_APEX_TASK_IDS: set[str] = set()
SLIGHT_APEX_TASK_IDS: set[str] = {
    "task_075c6f8ffb1548508e94e67e4ba04bbb",
    "task_3d4d03776d704758bb1bb9931e301b1c",
}

FALSE_POSITIVE_PATTERNS = [
    re.compile(r"strike price|crowdstrike|stock option", re.IGNORECASE),
    re.compile(r"s-?corp|s corporation|tax election", re.IGNORECASE),
    re.compile(r"lease|lessor|lessee|premises|commencement date|recapture", re.IGNORECASE),
    re.compile(r"remove(?:s)? redundancy|redundancy .*document|redundancy .*survey", re.IGNORECASE),
    re.compile(r"determination of exit requirement|pass/fail determination", re.IGNORECASE),
    re.compile(r"arbitration .*privacy|class.?action waivers", re.IGNORECASE),
]


def configure_stdout() -> None:
    """Use UTF-8 output when possible so Windows consoles do not crash on Unicode."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def matches(text: str) -> list[str]:
    """Return list of keyword patterns that matched in text."""
    hits = []
    for pattern in COMPILED:
        if pattern.search(text):
            hits.append(pattern.pattern)
    return hits


def snippet(text: str, keyword_pattern: str, context: int = 120) -> str:
    """Extract a short snippet around the first match."""
    m = re.search(keyword_pattern, text, re.IGNORECASE)
    if not m:
        return ""
    start = max(0, m.start() - context)
    end = min(len(text), m.end() + context)
    s = text[start:end]
    if start > 0:
        s = "..." + s
    if end < len(text):
        s = s + "..."
    return s.replace("\n", " ")


def is_probable_false_positive(text: str) -> bool:
    """Suppress common benchmark hits that match keywords but are not labor-relevant."""
    return any(pattern.search(text) for pattern in FALSE_POSITIVE_PATTERNS)


def classify_apex_task(task_id: str) -> str | None:
    if task_id in STRONG_APEX_TASK_IDS:
        return "strong"
    if task_id in SLIGHT_APEX_TASK_IDS:
        return "slight"
    return None


def write_examples_file() -> None:
    """Append a classified section without overwriting existing user notes."""
    existing = ""
    if EXAMPLES_PATH.exists():
        existing = EXAMPLES_PATH.read_text(encoding="utf-8").rstrip()

    marker = "## Agent-added classified examples"
    if marker in existing:
        existing = existing.split(marker, 1)[0].rstrip()

    lines = [existing, "", marker, "", "### Strong relevance", ""]
    for url, note in CURATED_EXAMPLES["strong"].items():
        lines.append(f"- {url}")
        lines.append(f"  - {note}")

    lines.extend(["", "### Slight relevance", ""])
    for url, note in CURATED_EXAMPLES["slight"].items():
        lines.append(f"- {url}")
        lines.append(f"  - {note}")

    content = "\n".join(part for part in lines if part != "")
    EXAMPLES_PATH.write_text(content + "\n", encoding="utf-8")
    total = len(CURATED_EXAMPLES["strong"]) + len(CURATED_EXAMPLES["slight"])
    print(f"Updated examples file without overwriting existing notes: {EXAMPLES_PATH} ({total} classified URLs)")


def search_apex_agents():
    print("=" * 80)
    print("APEX-AGENTS  (mercor/apex-agents)")
    print("=" * 80)

    # Download tasks_and_rubrics.json
    print("\nDownloading tasks_and_rubrics.json ...")
    path = hf_hub_download(
        repo_id="mercor/apex-agents",
        filename="tasks_and_rubrics.json",
        repo_type="dataset",
        token=HF_TOKEN,
    )
    with open(path, "r") as f:
        data = json.load(f)

    # The file is either a list of tasks or a dict with tasks
    if isinstance(data, dict):
        tasks = data.get("tasks", data.get("data", [data]))
        if not isinstance(tasks, list):
            tasks = [tasks]
    elif isinstance(data, list):
        tasks = data
    else:
        print(f"  Unexpected format: {type(data)}")
        return

    print(f"  Loaded {len(tasks)} tasks.\n")

    found = 0
    kept = 0
    for task in tasks:
        # Build searchable text from all string fields
        searchable_parts = []
        for key, val in task.items():
            if isinstance(val, str):
                searchable_parts.append(val)
            elif isinstance(val, list):
                for item in val:
                    if isinstance(item, str):
                        searchable_parts.append(item)
                    elif isinstance(item, dict):
                        for v in item.values():
                            if isinstance(v, str):
                                searchable_parts.append(v)
        searchable = " ".join(searchable_parts)

        hits = matches(searchable)
        if hits:
            if is_probable_false_positive(searchable):
                continue
            found += 1
            task_id = task.get("task_id", task.get("id", "unknown"))
            world_id = task.get("world_id", task.get("world", "unknown"))
            domain = task.get("domain", task.get("category", "unknown"))
            prompt = task.get("prompt", task.get("task", task.get("question", "")))
            classification = classify_apex_task(task_id)

            print(f"--- MATCH {found} ---")
            print(f"  Task ID : {task_id}")
            print(f"  World   : {world_id}")
            print(f"  Domain  : {domain}")
            print(f"  Keywords: {', '.join(hits)}")
            if classification:
                kept += 1
                print(f"  Keep    : {classification}")
            print(f"  Prompt  : {prompt[:300]}...")
            # Show a snippet for first keyword
            snip = snippet(searchable, hits[0])
            if snip:
                print(f"  Snippet : {snip}")
            print(f"  Explorer: https://apex-explorer.ooakdata.com/tasks/{task_id}")
            print()

    print(f"Total matches in APEX-Agents: {found} / {len(tasks)}\n")
    print(f"Classified APEX examples kept: {kept}\n")


def search_gdpval():
    print("=" * 80)
    print("GDPval  (openai/gdpval)")
    print("=" * 80)

    print("\nDownloading dataset ...")
    ds = load_dataset("openai/gdpval", split="train", token=HF_TOKEN)
    print(f"  Loaded {len(ds)} tasks.\n")

    found = 0
    for row in ds:
        task_id = row.get("task_id", "unknown")
        sector = row.get("sector", "unknown")
        occupation = row.get("occupation", "unknown")
        prompt = row.get("prompt", "")

        # Also search rubric if available
        rubric = row.get("rubric_pretty", "") or ""
        searchable = prompt + " " + rubric

        hits = matches(searchable)
        if hits:
            found += 1
            print(f"--- MATCH {found} ---")
            print(f"  Task ID   : {task_id}")
            print(f"  Sector    : {sector}")
            print(f"  Occupation: {occupation}")
            print(f"  Keywords  : {', '.join(hits)}")
            print(f"  Prompt    : {prompt[:300]}...")
            snip = snippet(searchable, hits[0])
            if snip:
                print(f"  Snippet   : {snip}")
            gdpval_url = f"https://www.gdpval.dev/{task_id}"
            print(f"  GDPval URL: {gdpval_url}")
            print()
    print(f"Total matches in GDPval: {found} / {len(ds)}\n")
    write_examples_file()


if __name__ == "__main__":
    configure_stdout()
    print("Searching benchmarks for labor-union-relevant tasks...\n")
    try:
        search_apex_agents()
    except Exception as e:
        print(f"Error searching APEX-Agents: {e}\n")
        if "gated" in str(e).lower() or "401" in str(e):
            print("Hint: set HF_TOKEN or HUGGINGFACE_HUB_TOKEN with access to mercor/apex-agents.\n")

    try:
        search_gdpval()
    except Exception as e:
        print(f"Error searching GDPval: {e}\n")

    print("Done.")
