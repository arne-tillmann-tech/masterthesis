"""
Schema for the legal-QA test corpus (Phase 1+2 TESTFRAGEN).

Records describe a single expert-authored legal question, optionally with a
reference answer (Phase 1) or with only a system prompt while a reference is
still pending (Phase 2). The manual evaluation grid (model output × material
level) is preserved from the source docx for downstream analysis but is not
consumed by the LLM-as-judge scorer.

Stored as JSONL — one Question per line. Phase 1 records live in
data/legal_qa/questions_with_reference.jsonl; Phase 2 records
(needs_reference=True) live in data/legal_qa/questions_pending_reference.jsonl.

Provisional — CAPS-T05 will promote this to the canonical schema.py once the
retired axis-pipeline schema is removed.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ── Constants ────────────────────────────────────────────────────────────────

QUESTION_ID_PATTERN = r"^Q-P[12]-[A-Z]{2}-\d{2}$"


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
    subtask_tag: Optional[str] = None
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
            raise ValueError("needs_reference=False but no reference_answer / reference_bullets")
        return self
