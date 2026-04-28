# Inter-Rater Reliability (IRR) Protocol (v1)

This document defines how the LLM-as-judge is validated against human expert
judgment. Without this validation, judge verdicts have no defensible
warrant — they are one model's opinion of another model's answer. The IRR
sample is what lets us claim the judge is doing what we want it to do.

**Status:** v1, 2026-04-28. **Two numerical defaults are PROVISIONAL pending
the deferred lit pass** (LIT-T03/T04 LLM-as-judge methodology + LIT-T05/T06
ordinal IRR). Both are flagged inline with `[PROVISIONAL]`. The structural
design (metric family, blinding, sampling strategy, fail-behavior) holds
independent of the lit revision.

## 1. Purpose

The IRR sample answers three questions:

1. **Judge–expert agreement.** Does the LLM judge produce verdicts that
   substantively agree with what a qualified human expert would assign?
   This is the primary validity check.
2. **Expert–expert agreement (ceiling).** Do two human experts even agree
   on the same items? This sets the ceiling for what the judge can
   plausibly achieve — a judge that matches the expert–expert level is at
   the limit of inter-human reliability.
3. **Judge–judge consistency (stochasticity).** Re-running the judge on
   the same inputs should produce identical verdicts at `temperature=0`.
   This is a sanity check, not a full IRR question.

The sample is executed at **M3** (Weeks 7–9) on the **frozen M2 corpus**
(≥50 questions). The protocol is designed now (M1, CAPS-T06) so the M2
corpus can be sized and stratified to support it.

## 2. Scope

- **Items rated:** (question, model_answer) pairs. The judge's task and
  the human rater's task are identical: read the question, the expert
  reference, and the model answer; assign one of three verdicts per
  `docs/judge-verdict-schema.md`.
- **Verdict scale:** the v1 3-level ordinal scale defined in
  `docs/judge-verdict-schema.md` (`worse_than_reference` /
  `on_par_with_reference` / `better_than_reference`). Edge cases EC-1/2/3
  in that document are part of the rule book raters apply.
- **Rater pool:** ≥ 2 qualified human experts (Alex's network: union
  legal officers, BR-trained lawyers, DIVA team members with legal
  background). Identity recorded as `expert_rater_id` in the `Verdict`
  schema for traceability.
- **Out of scope:** stance/tone/style/language judgments — explicitly
  *not measured* per `docs/judge-verdict-schema.md` §4.

## 3. Sample design

### 3.1 Sample size

**Target: N ≥ 30 questions [PROVISIONAL].** Each question rated
independently by ≥ 2 experts and by the LLM judge — so ≥ 90 verdicts at
N=30 with two experts.

**Why 30 is provisional:** This is a practical floor cited in
`MA-milestones.md` M3, derived from convention rather than power
calculation. Statistical caveat: with weighted Cohen's κ ≈ 0.6 at N=30,
the analytic standard error is approximately ±0.13, giving a 95% CI
roughly [0.34, 0.86]. That CI is wide enough that a point estimate alone
does not distinguish "moderate" from "almost perfect" agreement. The
**confidence interval must be reported alongside any κ point estimate**;
treating the bare point estimate as the threshold is not defensible.

**Lit pass should determine:**
- Whether 30 is sufficient given the 3-level ordinal structure (LIT-T05/T06
  ordinal-IRR sources).
- Whether the field convention for LLM-judge IRR samples (LIT-T03/T04, e.g.
  Zheng et al. 2023) supports a smaller or larger N for similar judging
  tasks.

### 3.2 Sampling strategy

**Stratified by `legal_subtask`** per `docs/legal-subtask-taxonomy.md`,
proportional to the M2 frozen corpus's subtask distribution, with a
**floor of 3 questions per in-construct subtask** to enable per-subtask
sanity checks.

In-construct subtasks (per taxonomy §4.3):
`paragraph_knowledge`, `multi_paragraph_synthesis`, `applied_fact_pattern`,
`procedural`, plus `strategic_practical` if retained at the M2 freeze.

**Across models.** The sample includes verdicts on answers from at least
3 systems-under-test from the planned model set (`MA-milestones.md` M4):
DIVA101 (if reachable at M3) plus ≥ 2 frontier models spanning
generations (e.g. `gpt-3.5-turbo` + `claude-sonnet-4`). Spreading verdicts
across model quality bands ensures the sample contains all three verdict
levels and is not biased toward a single regime.

**Within model × subtask cells.** Random selection from the M2 frozen
bank, seeded for reproducibility. Seed and selection script committed to
the repo at IRR-execution time.

## 4. Agreement metric

### 4.1 Primary metric

**Weighted Cohen's κ** for the 3-level ordinal scale, computed pairwise:

- judge ↔ expert_rater_1
- judge ↔ expert_rater_2
- expert_rater_1 ↔ expert_rater_2 (ceiling reference)

**Weighting scheme: linear weights** (i.e. `|i - j|/2` for a 3-level
scale, so `worse vs on_par` and `on_par vs better` each cost 0.5,
`worse vs better` costs 1.0). Linear is standard for short ordinal
scales; quadratic weights (e.g. squared difference) over-penalize
extreme disagreements when the scale has only three points and are not
preferred here.

### 4.2 If > 2 raters

**Krippendorff's α with ordinal weights.** Cohen's κ generalizes poorly
beyond pairwise; α handles arbitrary rater counts and missing data
cleanly. Computed alongside pairwise κ for transparency, not in place of
it. Threshold tiers below apply to α as well (Krippendorff's
recommendations are similar in shape: ≥ 0.667 for tentative inferences,
≥ 0.800 for strong claims; Krippendorff 2004).

### 4.3 Reporting

Every IRR result is reported as `<point estimate> [95% CI lower, upper]`.
Bootstrap CI (≥ 1000 resamples) preferred over the analytic SE for finite
N; bootstrap also handles the dependence structure across rater pairs.

## 5. Acceptance threshold

**Default: weighted Cohen's κ ≥ 0.6 [PROVISIONAL]** for the primary
judge ↔ expert_rater pair (averaged across the two expert raters, or
the single expert if only one is available).

**Why 0.6 is provisional:** Landis & Koch (1977) classified κ ∈ [0.61, 0.80]
as "substantial agreement" — a categorization built on no underlying
statistical derivation, just nameable bands. McHugh (2012) argues for
stricter thresholds in clinical settings. This benchmark's threshold
should be defended against domain-specific standards in the lit pass
(LIT-T03/T04 for LLM-judge work, LIT-T05/T06 for ordinal-IRR sources)
rather than adopted from a 1977 convention.

### 5.1 Action tiers (preliminary, for the LIT-T09 statistical analysis plan)

The protocol distinguishes degrees of failure:

| Pairwise weighted κ | Status      | Action                                    |
|---------------------|-------------|-------------------------------------------|
| ≥ 0.60              | Pass        | Judge accepted; proceed to M4 full runs.   |
| 0.50 – 0.59         | Caveat      | Proceed but flag in interpretation; document the disagreement clusters; consider judge prompt v2 (M3 deliverable). |
| 0.40 – 0.49         | Flag        | Halt full runs. Diagnose: rater confusion (rule book unclear) vs. judge bias (systematic verdict tilt). Iterate on judge prompt; re-sample. |
| < 0.40              | Contingency | Trigger `MA-milestones.md` Contingency Plan B (AI-pipeline fallback with reframed thesis contribution). Supervisor decision required. |

These thresholds are **also provisional** and tied to the LIT-T09 plan;
revise alongside §5's primary threshold.

## 6. Rater protocol

### 6.1 Independence

- Each rater rates each item independently — no consultation during
  rating.
- Raters do not see other raters' verdicts during rating. Rating order
  randomized per rater.

### 6.2 Blinding

For each item, raters see:

- the question (`question_text`)
- the expert reference (`reference_answer` and/or `reference_bullets`)
- the model answer (`raw_response`)

Raters do **not** see:

- the model identity (e.g. "gpt-4o" vs "DIVA101") — answers are presented
  with anonymized model labels (`model_A`, `model_B`, ...).
- the LLM judge's verdict or reasoning for the same item.
- the model's `legal_subtask` — taxonomy applies to questions, but raters
  should respond to what's actually in the answer, not a category label.

The rationale is to prevent both inter-rater anchoring and rater priors
about specific models from contaminating the verdict. Model-identity
unblinding happens only after all verdicts are collected.

### 6.3 Calibration round

Before independent rating, raters complete a **calibration round**
on 3–5 items (drawn from the M2 corpus but excluded from the IRR sample):

1. Each rater independently assigns a verdict.
2. Group discussion: walk through each item, surface disagreements, refer
   to `docs/judge-verdict-schema.md` for the rule book.
3. If disagreement on an item is rooted in an unclear edge case, log it
   for verdict-schema v2 revision (per `docs/judge-verdict-schema.md` §7).

Calibration items are not part of the IRR computation.

### 6.4 Rating environment

Spreadsheet or simple form. One row per item with: `question_id`,
`model_label_anonymized`, `question_text`, `reference`, `model_answer`,
`verdict` (dropdown: 3 levels), `reasoning` (1–3 sentences citing
specific evidence per `docs/judge-verdict-schema.md` §6).

Verdicts and reasoning saved to a JSONL conforming to the `Verdict` schema
in `schema.py` (CAPS-T05) with `expert_rater_id` populated.

## 7. What happens if it fails

Failure here means κ falls below the §5.1 "Pass" tier. The protocol does
**not** silently pass through low agreement.

- **Caveat tier (0.50–0.59).** Continue to M4 full runs but document the
  judge's reliability ceiling explicitly in M5 deliverables. Flag any
  thesis claims that depend on judge precision (especially fine-grained
  per-subtask comparisons) with the IRR caveat.
- **Flag tier (0.40–0.49).** **Halt full runs.** Diagnose the
  disagreement: cluster judge–expert mismatches by subtask, edge case,
  and disagreement direction (judge systematically more lenient? more
  strict?). Two responses available:
  1. Update the judge prompt (M3 deliverable: judge prompt v2). Re-run
     the IRR sample on the updated prompt.
  2. Tighten the verdict schema (`docs/judge-verdict-schema.md` v2). If
     the disagreement is rater-confusion rather than judge-quality,
     improving the rule book and re-running calibration may be sufficient.
  Re-sample only after the diagnosed change; do not iterate by re-rolling
  the same sample.
- **Contingency tier (< 0.40).** Trigger Contingency Plan B from
  `MA-milestones.md` (AI-pipeline pivot with reframed thesis). Supervisor
  notification per the Plan B protocol. Do not proceed to M4 full runs
  under the original framing.

The decision between caveat / flag / contingency is **not delegated** —
it requires supervisor sign-off (Alex). The IRR result is reported to the
supervisor with the full distribution of pairwise κ and the diagnostic
breakdown, not just the headline number.

## 8. Versioning + revision triggers

This is **v1**. Revise to v2 when any of the following occurs:

- **Lit pass completes (LIT-T03/T04 + LIT-T05/T06).** Threshold (§5),
  sample size (§3.1), and weighting scheme (§4.1) revisited against
  domain-specific evidence. Strip `[PROVISIONAL]` tags or replace
  defaults with lit-anchored values.
- **CAPS-T08 pilot exposes rater confusion** on cases not covered by
  the verdict schema's edge cases. Add edge cases to
  `docs/judge-verdict-schema.md` v2; revise the calibration-round
  guidance here.
- **M2 freeze decision drops `strategic_practical` or
  `composition_task`** from the corpus. Revise §3.2 stratification
  accordingly.
- **Recruited rater count is exactly 1** (single expert, e.g. only
  Alex available) — protocol degrades to judge ↔ expert single-pair
  IRR; expert ↔ expert ceiling is unobservable. Document this
  explicitly as a limitation.

Version history is tracked in this file's git history; do not maintain a
parallel changelog.

## References

- `docs/judge-verdict-schema.md` (the verdict construct raters and the
  judge both apply).
- `docs/legal-subtask-taxonomy.md` (the strata for the IRR sample).
- `MA-milestones.md` Locked Decision #5 + M3 (the IRR sample as an M3
  deliverable) + Contingency Plan B (the failure-tier escalation).
- `MA-weekly-microtasks.md` CAPS-T06 (this task), LIT-T03/T04/T05/T06
  (the deferred lit pass that revises the provisional defaults),
  LIT-T09 (the pre-specified statistical analysis plan that operationalizes
  §5.1).

### Citations supporting current defaults

- Cohen, J. (1960). A coefficient of agreement for nominal scales.
  *Educational and Psychological Measurement*, 20(1), 37–46.
  [Zotero key `PXCCFRXF`]
- Landis, J. R. & Koch, G. G. (1977). The measurement of observer
  agreement for categorical data. *Biometrics*, 33(1), 159–174.
  [Zotero key `E66MSSEW`]
