# Legal-Subtask Taxonomy (v1)

This document defines the legal-subtask categories the benchmark uses to
describe its question corpus and to track per-subtask judge performance. It
is the source of truth for the `LegalSubtask` enum in `schema.py` and the
`subtask_tag` field in `data/legal_qa/questions_*.jsonl`.

**Status:** v1, 2026-04-28. Revise after the CAPS-T08 pilot or the M2 freeze
review (see §5).

## 1. Purpose

The taxonomy serves three purposes in the legal-QA benchmark:

1. **Coverage tracking** — at the M2 freeze (≥50 questions), every subtask
   should be represented. A subtask with zero questions is a corpus gap that
   the GEN (AI-augmented) or UNION (commissioned) milestones must close.
2. **Per-subtask analysis** — judge verdicts and inter-rater reliability are
   sliced by subtask in M5–M6, so subtask-level skew (one subtask floors or
   ceilings) can be diagnosed and reported.
3. **Construct-fit gating** — two of the six subtasks are
   *eindeutig-prüfbar* borderline (see §2.5–2.6). Naming them explicitly
   surfaces the question of whether they belong in the v1 evaluation set
   rather than letting them silently shape results.

## 2. The six subtasks

Each subtask has: a one-line definition, an indicative question from the
corpus, and a *eindeutig-prüfbar* fit rating. The fit rating is a
methodological flag — it does not restrict which subtasks are scored, only
which subtasks the v1 construct (`MA-milestones.md` Pivot Note) was designed
to evaluate cleanly.

### 2.1 `paragraph_knowledge`

**Definition:** Direct doctrine recall about a specific Paragraph or named
statute. The answer is the content of one named norm.

**Indicative question:** *Q-P2-AM-07 — "Erkläre mir §80 des BetrVG."*

**Eindeutig-prüfbar fit:** **HIGH.** A correct answer cites the right
Paragraph and reproduces its substance; deviations are factually checkable.

### 2.2 `multi_paragraph_synthesis`

**Definition:** Combines multiple norms — across the BetrVG, or across the
BetrVG and other statutes (KSchG, BPersVG, ArbSchG, NPersVG, etc.) — into a
coherent picture. Includes conceptual distinctions and comparative-law
questions where the answer requires several anchor points.

**Indicative question:** *Q-P1-CZ-01 — "Welche Mitbestimmungsrechte hat der
Betriebsrat nach dem Betriebsverfassungsgesetz (BetrVG)?"* (answer spans
§ 87 across all eight subsections plus § 99, § 102, etc.)

**Eindeutig-prüfbar fit:** **HIGH.** Correctness criterion is "covers the
critical norms"; the reference enumerates them.

### 2.3 `applied_fact_pattern`

**Definition:** Apply legal norms to a concrete *Sachverhalt* the user
provides. The model must identify the relevant norms and conclude what
follows for the situation described.

**Indicative question:** *Q-P2-AM-05 — "Ich bin Werkstudentin in einer
Klinik — gilt das BetrVG für mich?"*

**Eindeutig-prüfbar fit:** **HIGH.** A correct answer identifies the
governing norm (e.g. § 5 BetrVG) and applies it to the facts; the
conclusion is binary or near-binary.

### 2.4 `procedural`

**Definition:** Formal-process how-to questions about Betriebsrat operations
(meetings, resolutions, committee formation, minutes, releases-from-duty).
Answers are recipe-shaped: "follow these steps, observe these formalities."

**Indicative question:** *Q-P1-AK-12 — "Wie läuft eine ordnungsgemäße
Betriebsratssitzung ab?"*

**Eindeutig-prüfbar fit:** **HIGH.** The answer enumerates statutory steps
(§ 29, § 30, § 33 BetrVG, etc.); a wrong step or missing formality is
factually checkable.

### 2.5 `strategic_practical`

**Definition:** Strategy-, soft-skill-, or best-practice-oriented questions
where the answer is mostly *advice* rather than *doctrine*. The legal layer
(if any) is thin and supports a practical recommendation.

**Indicative question:** *Q-P1-CZ-06 — "Welche Strategien gibt es, um
Vertrauen in der Belegschaft aufzubauen?"*

**Eindeutig-prüfbar fit:** **LOW — borderline.** There is no objectively
correct answer in the legal sense; reference answers reflect expert
judgment and good practice. Two qualified raters can reasonably disagree on
"better than reference" vs "on par." **Flag for M2 freeze review:** decide
whether these belong in the v1 benchmark or are split off into a separate
"practical-advisory" track.

### 2.6 `composition_task`

**Definition:** Asks the model to *produce a textual artifact* — a
statement, draft, position paper, example notice — rather than to answer a
question. Often (but not always) framed with a persona ("Du bist
Argumentationstrainer …").

**Indicative question:** *Q-P2-TK-16 — "Entwirf eine Betriebsvereinbarung
in Ansätzen."*

**Eindeutig-prüfbar fit:** **LOW — out-of-construct.** The legal-QA judge
construct ("model answer compared to expert reference answer") does not map
cleanly to artifact generation: there is no single correct draft, and what
counts as "better" is largely a writing-quality judgment. **Flag for M2
freeze review:** strong recommendation to either drop these from the v1
evaluation set or evaluate them under a separate construct (writing-task
quality), not under the legal-QA judge.

## 3. Question mapping

All 35 questions in the current corpus, classified. `phase` is the source
phase (1 = expert-authored with reference; 2 = expert-authored, reference
pending). Glosses are short paraphrases for orientation only — the
authoritative text lives in the JSONL.

| question_id  | phase | subtask                    | gloss |
|--------------|-------|----------------------------|-------|
| Q-P1-CZ-01   | 1     | multi_paragraph_synthesis  | Mitbestimmungsrechte des BR nach BetrVG |
| Q-P1-AM-02   | 1     | multi_paragraph_synthesis  | Unterschied Mitbestimmung vs. Mitwirkung |
| Q-P1-CZ-03   | 1     | multi_paragraph_synthesis  | Wichtige Gesetzestexte für BR / PR |
| Q-P1-CZ-04   | 1     | strategic_practical        | Umgang mit Interessenkonflikten Belegschaft↔UL |
| Q-P1-AM-05   | 1     | multi_paragraph_synthesis  | Zusammenarbeit BR mit Gewerkschaften |
| Q-P1-CZ-06   | 1     | strategic_practical        | Strategien für Vertrauen in der Belegschaft |
| Q-P1-CZ-07   | 1     | paragraph_knowledge        | Besonderer Kündigungsschutz BR-Mitglieder |
| Q-P1-AM-08   | 1     | strategic_practical        | Versachlichung bei aufgeheizter BR-Wahl |
| Q-P1-CZ-09   | 1     | multi_paragraph_synthesis  | Fristen für Stellungnahmen / Widersprüche |
| Q-P1-CZ-10   | 1     | multi_paragraph_synthesis  | Mitbestimmung Personalrat Niedersachsen (NPersVG) |
| Q-P1-AK-11   | 1     | multi_paragraph_synthesis  | Einflussmöglichkeiten BR bei KI-Einführung |
| Q-P1-AK-12   | 1     | procedural                 | Ablauf einer ordnungsgemäßen BR-Sitzung |
| Q-P1-AK-13   | 1     | procedural                 | Formalien bei Beschlüssen |
| Q-P1-AK-14   | 1     | procedural                 | Ausschüsse bilden / Aufgaben delegieren |
| Q-P1-AK-15   | 1     | paragraph_knowledge        | Freistellung von Betriebsräten (§ 38 BetrVG) |
| Q-P1-AM-16   | 1     | multi_paragraph_synthesis  | Aufgaben BR ggü. Belegschaft und AG |
| Q-P1-AM-17   | 1     | procedural                 | Protokollformat, Datenschutz, Firmenprogramme |
| Q-P1-AM-18   | 1     | strategic_practical        | Anwalt finden / schnell kontaktieren |
| Q-P2-AM-01   | 2     | composition_task           | Argumentationstrainer: Stellungnahme zu E-Mail |
| Q-P2-AM-02   | 2     | paragraph_knowledge        | §§ 2 BetrVG einfach zusammenfassen |
| Q-P2-AM-03   | 2     | applied_fact_pattern       | Handy-Verbot: Gesetzespyramide-Ebene + BR-Recht |
| Q-P2-AM-04   | 2     | applied_fact_pattern       | § 5 BetrVG für BR-Mitglied im Krankenhaus |
| Q-P2-AM-05   | 2     | applied_fact_pattern       | Werkstudentin Klinik: gilt BetrVG? |
| Q-P2-AM-06   | 2     | applied_fact_pattern       | Welche BetrVG-Organe existieren im Kindergarten |
| Q-P2-AM-07   | 2     | paragraph_knowledge        | § 80 BetrVG erklären |
| Q-P2-AM-08   | 2     | composition_task           | Statement digitale Weiterbildung formulieren |
| Q-P2-CZ-12   | 2     | paragraph_knowledge        | Inklusionsförderung nach § 80 BetrVG |
| Q-P2-CZ-13   | 2     | applied_fact_pattern       | Was tun wenn Barrieren nicht beseitigt werden |
| Q-P2-TK-14   | 2     | composition_task           | Argumentationspapier Azubiübernahme |
| Q-P2-TK-15   | 2     | strategic_practical        | BR aktive Gestaltung der Ausbildung |
| Q-P2-TK-16   | 2     | composition_task           | Betriebsvereinbarung in Ansätzen entwerfen |
| Q-P2-TK-17   | 2     | strategic_practical        | Familienfreundliche Arbeitszeiten fördern |
| Q-P2-TK-18   | 2     | composition_task           | Mini-Initiative zur Arbeitsumgebung |
| Q-P2-TK-19   | 2     | multi_paragraph_synthesis  | Rolle BR bei Gesundheitsschutz |
| Q-P2-TK-20   | 2     | composition_task           | Beispiel-Aushang zum Thema Sprache |

## 4. Coverage observations

### 4.1 Per-subtask counts

| Subtask                    | Phase 1 | Phase 2 | Total |
|----------------------------|---------|---------|-------|
| paragraph_knowledge        | 2       | 3       | 5     |
| multi_paragraph_synthesis  | 8       | 1       | 9     |
| applied_fact_pattern       | 0       | 5       | 5     |
| procedural                 | 4       | 0       | 4     |
| strategic_practical        | 4       | 2       | 6     |
| composition_task           | 0       | 6       | 6     |
| **Total**                  | **18**  | **17**  | **35** |

### 4.2 Phase-1-only coverage gaps

The v1 evaluation set is **Phase 1 only** (the 18 questions with consolidated
expert references; Phase 2 questions still need reference-answer
consolidation per the M2 protocol). Two structural gaps in Phase 1:

- **Zero `applied_fact_pattern` questions.** This is the canonical
  legal-QA shape — "given facts, apply law" — and the construct is at its
  most defensible here. **GEN-T01/T02 should prioritize this subtask** to
  close the gap before the M2 freeze.
- **Zero `composition_task` questions.** Less concerning — under §2.6
  these are out-of-construct anyway; if they're dropped from v1, the gap
  resolves itself.

Phase-1 is also skewed toward `multi_paragraph_synthesis` (8/18 = 44%).
That's not a problem in itself but should be tracked: if the trennschärfe
check (CAPS-T09) shows judge performance varies sharply between subtasks,
the synthesis-heavy mix could mask issues elsewhere.

### 4.3 Construct-fit summary

- **In-construct (5 subtasks, 23/35 questions):** `paragraph_knowledge`,
  `multi_paragraph_synthesis`, `applied_fact_pattern`, `procedural`, plus
  the high-fit boundary case `strategic_practical` if the M2 freeze
  retains it.
- **Borderline (1 subtask, 6 questions):** `strategic_practical` —
  decision pending M2 freeze.
- **Out-of-construct (1 subtask, 6 questions):** `composition_task` —
  recommend dropping from v1 evaluation set or splitting to a separate
  writing-quality track.

## 5. Versioning + revision triggers

This is **v1**. Revise to v2 if any of the following occurs:

- **CAPS-T08 pilot inspection** reveals the judge cannot discriminate
  meaningfully within a subtask (verdicts cluster at one level regardless
  of model) → the subtask is too coarse or too fine; split or merge.
- **CAPS-T09 trennschärfe check** shows one subtask floors or ceilings
  for all models → re-examine question difficulty within that subtask.
- **M2 freeze review** decides `strategic_practical` and/or
  `composition_task` are out-of-construct for v1 → drop from corpus and
  re-issue mapping.
- **GEN milestone or UNION milestone** introduces questions that don't
  fit any of the six subtasks cleanly → add a seventh subtask only with
  explicit supervisor sign-off (Assumption #3 of `MA-milestones.md`: no
  new primary-measurement construct after M3).

Version history is tracked in this file's git history; do not maintain a
parallel changelog.

## References

- `MA-milestones.md` Pivot Note (the legal-QA construct this taxonomy
  describes) and Question schema (the data structure `subtask_tag` lives
  in).
- `MA-weekly-microtasks.md` CAPS-T02 (this task's definition) +
  CAPS-T05 (where the `LegalSubtask` enum is implemented in `schema.py`).
- `data/legal_qa/questions_with_reference.jsonl` and
  `questions_pending_reference.jsonl` (the corpus this taxonomy
  describes; `subtask_tag` populated as part of CAPS-T02).
- `docs/judge-verdict-schema.md` (the verdict construct that operates on
  questions classified by this taxonomy).
