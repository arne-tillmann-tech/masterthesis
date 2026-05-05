"""
Canonical schemas for the legal-QA output-quality benchmark.

Three core models:
  1. Question  – an expert-authored legal question with optional reference
                 answer (the input + gold standard).
  2. ModelEvaluation – one column of one source-docx evaluation table; carried
                       through from Phase-1/2 ingest for downstream analysis,
                       not consumed by the LLM-as-judge scorer.
  3. Verdict   – one judge verdict over a (question, model_response) pair.
                 IRR-sample rows additionally carry the matching human expert
                 verdict, joined by `irr_pair_id`.

Two enums:
  - LegalSubtask – the v1 taxonomy from `docs/legal-subtask-taxonomy.md`.
  - JudgeVerdict – the v1 3-level scale from `docs/judge-verdict-schema.md`.

Replaces the v0.1 axis-pipeline schema (`Domain`, `Role`, `Jurisdiction`,
`AxisPole`, `GoldAxisTargets`, `Scenario`, `Annotation`, `RefusalClass`).
The v0.1 schema is preserved at git tag `v0.1-axis-pipeline` for historical
reference and is not active. See `MA-milestones.md` Pivot Note for context.

Stored as JSONL — one record per line.
  - data/legal_qa/questions_with_reference.jsonl     — Question (Phase 1)
  - data/legal_qa/questions_pending_reference.jsonl  — Question (Phase 2)
  - (Verdict JSONL paths defined per evaluation run; Inspect AI logs are the
     primary verdict store today.)
"""

from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import (
    BaseModel,
    Field,
    computed_field,
    field_validator,
    model_validator,
)


# ── Constants ────────────────────────────────────────────────────────────────

QUESTION_ID_PATTERN = r"^Q-P[12]-[A-Z]{2}-\d{2}$"


# ── Enums ────────────────────────────────────────────────────────────────────


class LegalSubtask(str, Enum):
    """v1 legal-subtask taxonomy. Source of truth: `docs/legal-subtask-taxonomy.md`."""

    paragraph_knowledge = "paragraph_knowledge"
    multi_paragraph_synthesis = "multi_paragraph_synthesis"
    applied_fact_pattern = "applied_fact_pattern"
    procedural = "procedural"
    strategic_practical = "strategic_practical"
    composition_task = "composition_task"


class JudgeVerdict(str, Enum):
    """v1 3-level verdict scale. Source of truth: `docs/judge-verdict-schema.md`."""

    worse_than_reference = "worse_than_reference"
    on_par_with_reference = "on_par_with_reference"
    better_than_reference = "better_than_reference"


# Verdicts that count as "correct" in the binary derivation
# (`docs/judge-verdict-schema.md` §3).
_PASSING_VERDICTS = frozenset(
    {JudgeVerdict.on_par_with_reference, JudgeVerdict.better_than_reference}
)


# ── ModelEvaluation (one column of one source-doc table) ─────────────────────


class ModelEvaluation(BaseModel):
    """One column of one evaluation table from the source docx.

    Phase 1: 3 tables × 4 columns (Öff. Mat., + Gew. Mat., + bund Mat., plus the
    leading row-label column which is skipped here).
    Phase 2: 2 tables; the Öff. Mat. column is sometimes dropped.
    """

    table_index: int = Field(..., ge=1)
    material_level: str = Field(..., min_length=1)
    answer: Optional[str] = None
    response_time: Optional[str] = None
    references_cited: Optional[str] = None
    human_evaluation: Optional[str] = None
    second_person_diff: Optional[str] = None  # Phase 2 only


# ── Question (one TESTFRAGE) ─────────────────────────────────────────────────


class Question(BaseModel):
    """One expert-authored legal question, optionally with a reference answer.

    Phase 1 records have a populated reference (`reference_answer` and/or
    `reference_bullets`); Phase 2 records have `needs_reference=True` and no
    reference yet (M2 corpus expansion produces them).
    """

    question_id: str = Field(..., pattern=QUESTION_ID_PATTERN)
    phase: Literal[1, 2]
    author_initials: str = Field(..., min_length=2, max_length=2)
    question_number: int = Field(..., ge=1)
    language: Literal["de"] = "de"

    question_text: str = Field(..., min_length=10)
    system_prompt: Optional[str] = None
    reference_answer: Optional[str] = None
    reference_bullets: Optional[list[str]] = None

    model_evaluations: list[ModelEvaluation] = Field(default_factory=list)

    source_docx: str = Field(..., min_length=1)
    extracted_at: str = Field(..., min_length=10)
    subtask_tag: Optional[LegalSubtask] = None
    needs_reference: bool = False
    review_status: Literal["unreviewed", "reviewed", "approved"] = "unreviewed"

    @field_validator("author_initials")
    @classmethod
    def initials_uppercase(cls, v: str) -> str:
        if not (v.isalpha() and v.isupper()):
            raise ValueError("author_initials must be exactly 2 uppercase letters")
        return v

    @model_validator(mode="after")
    def check_id_matches_metadata(self) -> "Question":
        expected = f"Q-P{self.phase}-{self.author_initials}-{self.question_number:02d}"
        if self.question_id != expected:
            raise ValueError(
                f"question_id {self.question_id!r} does not match metadata "
                f"(expected {expected!r})"
            )
        return self

    @model_validator(mode="after")
    def check_reference_consistency(self) -> "Question":
        has_ref = bool(self.reference_answer or self.reference_bullets)
        if self.needs_reference and has_ref:
            raise ValueError("needs_reference=True but a reference answer is present")
        if not self.needs_reference and not has_ref:
            raise ValueError(
                "needs_reference=False but no reference_answer / reference_bullets"
            )
        return self


# ── Verdict (one judge verdict over a (question, model_response) pair) ──────


class Verdict(BaseModel):
    """One judge verdict, optionally paired with a human expert verdict for IRR.

    Routine eval rows have only the judge fields populated. IRR-sample rows
    additionally carry `expert_rater_id` + `expert_verdict_3level`, with
    `irr_pair_id` joining the rows that compare on the same item.

    Binary verdicts (`judge_verdict_binary`, `expert_verdict_binary`) are
    derived from the 3-level fields per `docs/judge-verdict-schema.md` §3 —
    `correct = on_par OR better`. They are computed properties: any value
    supplied at construction time is ignored. This keeps the binary in sync
    with the 3-level by construction.
    """

    # ── Identity ────────────────────────────────────────────────────────────
    question_id: str = Field(..., pattern=QUESTION_ID_PATTERN)
    model_name: str = Field(..., min_length=1, description="e.g. gpt-4o, claude-sonnet-4-20250514")
    model_version: Optional[str] = None
    run_config: dict = Field(default_factory=dict, description="decoding params + run-specific config")
    raw_response: str = Field(..., min_length=1, description="the model answer that was judged")

    # ── Judge ───────────────────────────────────────────────────────────────
    judge_id: str = Field(..., min_length=1, description="judge model identifier")
    judge_verdict_3level: JudgeVerdict
    judge_explanation: str = Field(..., min_length=1, description="1–3 sentences citing concrete evidence (per judge-verdict-schema.md §6)")

    # ── Human expert (only set for IRR-sample rows) ────────────────────────
    expert_rater_id: Optional[str] = None
    expert_verdict_3level: Optional[JudgeVerdict] = None
    irr_pair_id: Optional[str] = Field(
        None,
        description="joins rows that rate the same (question, model_response) item across raters",
    )

    # ── Free-form ──────────────────────────────────────────────────────────
    notes: str = ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def judge_verdict_binary(self) -> bool:
        """`correct = on_par OR better` per docs/judge-verdict-schema.md §3."""
        return self.judge_verdict_3level in _PASSING_VERDICTS

    @computed_field  # type: ignore[prop-decorator]
    @property
    def expert_verdict_binary(self) -> Optional[bool]:
        """Expert binary verdict, derived from 3-level. None if not human-rated."""
        if self.expert_verdict_3level is None:
            return None
        return self.expert_verdict_3level in _PASSING_VERDICTS

    @model_validator(mode="after")
    def check_expert_consistency(self) -> "Verdict":
        has_rater = self.expert_rater_id is not None
        has_verdict = self.expert_verdict_3level is not None
        if has_rater != has_verdict:
            raise ValueError(
                "expert_rater_id and expert_verdict_3level must be set together "
                "(or both None)"
            )
        if self.irr_pair_id is not None and not has_verdict:
            raise ValueError(
                "irr_pair_id set but no expert verdict — IRR rows require an "
                "expert rating"
            )
        return self


# ── DivaResponse (one streamed DIVA101 call, persisted for playback) ────────


class DivaResponse(BaseModel):
    """One streamed DIVA101 call: (SUT × Arcana tier × question) → response.

    Persisted to JSONL by `scripts/diva_fetch.py`. The Inspect-AI evaluation
    task replays these via the `diva_playback` solver, decoupling the
    long-running streaming RAG fetch from the (judge-driven) scoring step.

    Required because Inspect-AI's `OpenAICompatibleAPI` cannot enable HTTP
    streaming via `extra_body={"stream": true}` (the SDK's hard cast at
    `openai_compatible.py:290` rejects the resulting `AsyncStream`), but
    DIVA101's SAIA gateway requires `stream: true` plus the
    `inference-service: saia-openai-gateway` header to invoke Arcana
    retrieval — non-streaming requests hit a server-side ~10s ReadTimeout
    before the qwen reasoning preamble finishes.
    """

    # ── Identity ────────────────────────────────────────────────────────────
    question_id: str = Field(..., pattern=QUESTION_ID_PATTERN)
    sut_model: str = Field(..., min_length=1, description="GWDG model id, e.g. 'qwen3.5-397b-a17b'")
    rag_label: str = Field(..., min_length=1, description="human label, e.g. 'Öff. Mat.'")
    arcana_id: str = Field(..., min_length=1, description="Arcana RAG id, e.g. 'ananyapam.de01/Betriebsverfassungsgesetz'")

    # ── Response ────────────────────────────────────────────────────────────
    raw_response: str = Field(..., description="full concatenated streamed text (incl. inlined [RREF] markers)")
    rref_markers: list[str] = Field(default_factory=list, description="extracted '[RREF<N>] filename p.X,y:Y (relevance)' tokens, verbatim")
    finish_reason: Optional[str] = None

    # ── Run metadata ────────────────────────────────────────────────────────
    fetched_at: str = Field(..., min_length=10, description="ISO-8601 UTC timestamp of when the call returned")
    elapsed_s: float = Field(..., ge=0.0, description="wall-clock seconds for the streamed call")
    error: Optional[str] = Field(None, description="exception text if the call failed; raw_response will be empty")
