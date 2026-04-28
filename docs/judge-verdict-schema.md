# Judge Verdict Schema (v1)

This document defines the verdict the LLM-as-judge produces when comparing a
model answer to an expert reference answer. It is the rule book for both the
judge prompt (`judge_template.txt`, drafted in CAPS-T04) and human raters in
the inter-rater reliability sample (`docs/irr-protocol.md`, drafted in CAPS-T06).

**Status:** v1, 2026-04-28. Revise after the CAPS-T08 pilot if any edge case
turns out unused, raters disagree on a case not covered, or the judge produces
a verdict pattern that contradicts an edge-case ruling.

## 1. Construct

The judge measures **legal-QA output quality**: whether a model's answer to a
real labor-law practice question is correct, complete, and cites the right
paragraphs, judged against an expert-authored reference answer.

This replaces the v0.1 4-axis stance rubric (preserved at git tag
`v0.1-axis-pipeline`). The axis rubric measured the model's *posture* on
labor issues — solidarity-vs-confrontative, collective-vs-individual,
rights-aware-vs-rights-blind, actionable-vs-vague. The 2026-04-14 DIVA-team
alignment narrowed scope to legal-QA correctness: the question now is whether
the model's answer is *substantively right*, not whether it takes a particular
stance. See `MA-milestones.md` Pivot Note for full context.

## 2. Three-level verdict scale

The judge assigns exactly one of three levels per (question, model answer) pair:

### `worse_than_reference`

The model answer is substantively worse than the expert reference along at
least one of the comparison dimensions (correctness, completeness, citation
accuracy). Typical evidence: a factual or legal error, a missing critical
point that the reference includes, an invented or misattributed Paragraph
number, or a refusal/hedge that doesn't engage the question. Stylistic
differences alone do not justify this verdict.

### `on_par_with_reference`

The model answer matches the reference's substantive coverage along all three
comparison dimensions. The legal conclusion is the same (or an equivalent
alternative is correctly supported); the critical points are present;
citations are correct, whether they match the reference exactly or substitute
valid alternatives. Minor differences in ordering, phrasing, or non-critical
detail are not penalized.

### `better_than_reference`

The model answer covers everything the reference does correctly AND adds
substantive value the reference omits — for example, additional correct legal
points, more complete citation of relevant Paragraphs, or a useful nuance or
caveat the expert reference did not include. The "extra" must be correct;
verbose-but-wrong content does not earn this verdict.

## 3. Binary derivation

`correct = on_par_with_reference OR better_than_reference`

Rationale: the expert reference is calibrated to the *minimum acceptable
expert answer*. Matching it earns full credit; only `worse_than_reference` is
a quality failure. The binary is computed downstream from the 3-level verdict
— the judge does not output it directly.

## 4. Comparison dimensions

The judge compares model answer to reference along three implicit dimensions:

- **Correctness** — does the answer arrive at the right legal conclusion and
  avoid factual or doctrinal errors?
- **Completeness** — does the answer cover the critical legal points the
  reference covers (and ideally no fewer)?
- **Citation accuracy** — when the answer cites a Paragraph, statute, or
  case, is that citation real and applicable?

These dimensions are weighed holistically into a single 3-level verdict. The
judge does not score them separately.

### What is deliberately NOT measured

- **Stance.** The model's posture on labor issues (e.g.
  solidarity-vs-confrontative, pro-worker-vs-pro-employer). This was the
  v0.1 axis-rubric construct; the 14.4 alignment dropped it. Two answers
  that reach the same correct legal conclusion via different stances both
  earn `on_par_with_reference`.
- **Tone or style.** Verbose, terse, formal, casual — irrelevant if the
  substance is right.
- **Language match.** If the reference is in German and the model answers
  in English (or vice versa), that alone does not lower the verdict.
  Substance is what's compared.

## 5. Edge cases (v1)

These are the rulings raters and the judge prompt should apply when the
default scale anchors are ambiguous. Three entries for v1; held back for v2
unless the pilot reveals a gap: paragraph hallucination with correct
conclusion; language mismatch as a borderline case.

### EC-1: Model answer is more comprehensive than the reference

Model answer covers everything the reference covers correctly AND adds extra
correct legal content the reference omits (e.g. cites an additional relevant
Paragraph, raises a valid procedural caveat).

**Verdict:** `better_than_reference`.

**Why:** The reference is the minimum bar; correctly exceeding it is what
this verdict level is for. The "extra" must be correct — verbose-but-wrong
filler does not qualify.

### EC-2: Model answer cites a different Paragraph that is also correct

The reference cites Paragraph X; the model cites Paragraph Y instead, where
Y is a valid alternative legal basis for the same conclusion (e.g. the
reference uses § 615 BGB and the model uses § 326 BGB to reach the same
result).

**Verdict:** `on_par_with_reference`.

**Why:** Correctness is the construct, not citation identity. The judge
should not penalize a substantively correct answer for choosing a different
valid legal basis. (If unsure whether the alternative citation is actually
valid, default to `worse_than_reference` and flag in the explanation — the
disagreement-analysis pass picks these up.)

### EC-3: Model refuses or hedges without engaging the question

Model answer is some variant of "I cannot give legal advice; please consult
a lawyer," with no substantive engagement with the legal question.

**Verdict:** `worse_than_reference`.

**Why:** Under the legal-QA construct, refusal is a quality failure — the
question is whether the model answers correctly, and a non-answer is
incorrect by default. This is distinct from the v0.1 categorical refusal
class, which treated refusal as a separate dimension. Here it collapses
into the 3-level verdict.

## 6. Output format

The judge produces:

```json
{
  "verdict": "worse_than_reference" | "on_par_with_reference" | "better_than_reference",
  "explanation": "<1–3 sentences citing specific evidence from the model answer>"
}
```

The explanation must reference concrete content of the model answer (e.g.
"answer omits the § 87 BetrVG Mitbestimmungsrecht the reference cites") so
disagreement analysis can later identify systematic patterns.

## 7. Versioning + revision triggers

This is **v1**. Revise to v2 after the CAPS-T08 pilot if any of the
following occurs:

- An edge case (EC-1/2/3) is never invoked across the pilot's 30 verdicts
  → drop or replace.
- Two raters disagree on a question whose ruling is not covered by the
  scale anchors or edge cases → add an edge case.
- The judge produces a verdict pattern that contradicts an edge-case
  ruling (e.g. systematically grades EC-2 cases as `worse_than_reference`)
  → tighten the prompt language for that case.

Version history is tracked in this file's git history; do not maintain a
parallel changelog.

## References

- `MA-milestones.md` Pivot Note + Judge methodology section (the source
  this doc lifts from; this doc is the standalone collaborator-facing form).
- `MA-weekly-microtasks.md` CAPS milestone (task definitions, dependency
  order).
- Git tag `v0.1-axis-pipeline` (the retired axis rubric — preserved for
  historical reference, not active).
