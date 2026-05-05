#!/usr/bin/env python3
"""Print a slice of grading samples from bundle.jsonl in clean text form.

Usage: python grader_sample.py START [END] [--cell SUT__TIER]

Without --cell, prints rows START..END (0-indexed, half-open) from the full
bundle. With --cell, filters first to that cell then slices.
The gpt5mini_verdict and gpt5mini_reasoning fields are NEVER printed
(blind grading by design).
"""
import json
import sys
from pathlib import Path

BUNDLE = Path('/home/arne/masterthesis/data/grader_compare/bundle.jsonl')


def trim_response(resp: str) -> str:
    """Cut the [RREF...] verbatim BetrVG dump that DIVA appends to many answers.

    Many DIVA responses end with `-----------------------------------------\nReferences:\n[RREF1] ...`
    showing the verbatim corpus text. The grader only needs the answer body,
    not the source-text dumps (those bloat sample size for the LLM grader).
    """
    markers = ['\n-----------------------------------------\nReferences:', '\n----\nReferences:', '\nReferences:\n[RREF']
    for m in markers:
        i = resp.find(m)
        if i != -1:
            return resp[:i].rstrip() + '\n\n[NOTE: verbatim [RREF...] BetrVG corpus dump truncated]'
    return resp


def main(argv: list[str]) -> int:
    cell_filter: str | None = None
    trim = True
    args: list[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == '--cell':
            cell_filter = argv[i + 1]
            i += 2
        elif a == '--no-trim':
            trim = False
            i += 1
        else:
            args.append(a)
            i += 1
    if not args:
        print('usage: grader_sample.py START [END] [--cell sut__tier] [--no-trim]', file=sys.stderr)
        return 1
    start = int(args[0])
    end = int(args[1]) if len(args) > 1 else start + 1

    rows = []
    with open(BUNDLE) as f:
        for line in f:
            r = json.loads(line)
            if cell_filter and f"{r['sut']}__{r['tier']}" != cell_filter:
                continue
            rows.append(r)
    rows = rows[start:end]
    for idx, r in enumerate(rows, start=start):
        print(f'\n========== ROW {idx}  cell_id={r["cell_id"]} ==========')
        print(f'subtask: {r["subtask_tag"]}')
        print(f'\n--- FRAGE ---\n{r["question_text"]}')
        print(f'\n--- REFERENZ ---\n{r["reference"]}')
        resp = trim_response(r["response"]) if trim else r["response"]
        print(f'\n--- MODELLANTWORT ---\n{resp}')
        print()
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
