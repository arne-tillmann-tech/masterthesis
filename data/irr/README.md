# IRR sample materials (v1)

Generated 2026-04-29 from the v2-prompt × gpt-5-mini-grader DIVA matrix.

## Files
- `irr_sample_v1.md` — N=30 stratified items for double-blind rating per `docs/irr-protocol.md` §3.2.
- `calibration_v1.md` — 5 calibration items (use BEFORE main sample per §6.3).
- `_unblinding_key_v1.json` — **gitignored**. Maps row_id → (model, rag, judge verdict). Do NOT share with raters until they finish.

## How to use
1. Each rater opens `irr_sample_v1.md`, fills checkboxes + reasoning, saves as `irr_sample_v1__<rater_id>.md`.
2. After all raters finish, compute pairwise weighted Cohen's κ (judge ↔ rater_1, judge ↔ rater_2, rater_1 ↔ rater_2) per §4.
3. Report point estimate + 95% bootstrap CI per §4.3.

## Stratification (sample, N=30)
| Subtask | N | % |
|---|---:|---:|
| multi_paragraph_synthesis | 11 | 37% |
| procedural | 7 | 23% |
| strategic_practical | 7 | 23% |
| paragraph_knowledge | 5 | 17% |

## Caveats
- Phase-1 only (18 unique questions; valid (q, config) pool: 132 after dropping cancelled samples from config 6).
- Anonymization: 8 model_configs labeled model_A through model_H, randomly assigned (seed=42).
- Rater pool target: ≥2 per protocol §3.1. Single-rater fallback degrades to judge↔expert pairwise only (§8).
