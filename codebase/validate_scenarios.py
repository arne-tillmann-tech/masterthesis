"""
Validate JSONL scenario files against the canonical schema.

Usage:
    python validate_scenarios.py <path_to_scenarios.jsonl>
    python validate_scenarios.py            # defaults to ../data/scenarios/scenarios.jsonl
"""

import json
import sys
from collections import Counter
from pathlib import Path

from pydantic import ValidationError

from schema import Scenario, Domain, Role, Jurisdiction

DEFAULT_PATH = Path(__file__).parent.parent / "data" / "scenarios" / "scenarios.jsonl"


def load_and_validate(filepath: Path) -> tuple[list[Scenario], list[dict]]:
    """Return (valid_scenarios, error_records)."""
    valid: list[Scenario] = []
    errors: list[dict] = []

    with open(filepath, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as e:
                errors.append({"line": line_num, "error": f"JSON parse error: {e}"})
                continue

            try:
                scenario = Scenario(**data)
                valid.append(scenario)
            except ValidationError as e:
                errors.append({
                    "line": line_num,
                    "scenario_id": data.get("scenario_id", "???"),
                    "error": str(e),
                })

    return valid, errors


def check_duplicates(scenarios: list[Scenario]) -> list[str]:
    """Return list of duplicate scenario IDs."""
    ids = [s.scenario_id for s in scenarios]
    counts = Counter(ids)
    return [sid for sid, n in counts.items() if n > 1]


def print_coverage(scenarios: list[Scenario]) -> None:
    """Print coverage matrix: domain × role."""
    grid: dict[str, dict[str, int]] = {}
    for d in Domain:
        grid[d.value] = {r.value: 0 for r in Role}

    for s in scenarios:
        grid[s.domain.value][s.role_prompt.value] += 1

    # Header
    roles = [r.value for r in Role]
    header = f"{'domain':<25}" + "".join(f"{r:<12}" for r in roles) + "total"
    print("\n" + "=" * len(header))
    print("COVERAGE MATRIX: domain × role")
    print("=" * len(header))
    print(header)
    print("-" * len(header))

    grand_total = 0
    for domain, role_counts in grid.items():
        row_total = sum(role_counts.values())
        grand_total += row_total
        row = f"{domain:<25}" + "".join(f"{role_counts[r]:<12}" for r in roles) + str(row_total)
        print(row)

    print("-" * len(header))
    col_totals = {r: sum(grid[d][r] for d in grid) for r in roles}
    totals_row = f"{'TOTAL':<25}" + "".join(f"{col_totals[r]:<12}" for r in roles) + str(grand_total)
    print(totals_row)

    # Jurisdiction distribution
    jur_counts = Counter(s.jurisdiction_context.value for s in scenarios)
    print(f"\nJurisdiction distribution: {dict(jur_counts)}")

    # Cross-cut stats
    n = len(scenarios)
    refusal_traps = sum(1 for s in scenarios if s.refusal_trap)
    ambiguous = sum(1 for s in scenarios if s.ambiguity_flag)
    diff_counts = Counter(s.difficulty.value for s in scenarios)
    source_counts = Counter(s.source.value for s in scenarios)

    print(f"Refusal traps:  {refusal_traps}/{n} ({100*refusal_traps/n:.0f}%)" if n else "")
    print(f"Ambiguity flag: {ambiguous}/{n} ({100*ambiguous/n:.0f}%)" if n else "")
    print(f"Difficulty:     {dict(diff_counts)}")
    print(f"Source:         {dict(source_counts)}")
    print(f"Review status:  {dict(Counter(s.review_status.value for s in scenarios))}")


def main() -> int:
    filepath = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PATH

    if not filepath.exists():
        print(f"ERROR: File not found: {filepath}")
        return 1

    scenarios, errors = load_and_validate(filepath)

    print(f"\nValidated {len(scenarios)} scenarios from {filepath.name}")

    if errors:
        print(f"\n⚠ {len(errors)} VALIDATION ERRORS:")
        for e in errors:
            print(f"  Line {e['line']}: {e.get('scenario_id', '')} → {e['error'][:200]}")
    else:
        print("✓ All scenarios pass schema validation.")

    dupes = check_duplicates(scenarios)
    if dupes:
        print(f"\n⚠ DUPLICATE IDs: {dupes}")
    else:
        print("✓ No duplicate scenario IDs.")

    if scenarios:
        print_coverage(scenarios)

    return 1 if errors or dupes else 0


if __name__ == "__main__":
    sys.exit(main())
