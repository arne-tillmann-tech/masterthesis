"""
Canonical schema definitions for the union-perspective LLM benchmark.

Three schemas:
  1. Scenario  – the benchmark prompts (input to models)
  2. ModelOutput – raw model responses
  3. Annotation – human/AI ratings per axis

All data is stored as JSONL (one JSON object per line).
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ── Enums ────────────────────────────────────────────────────────────────────

class Domain(str, Enum):
    organizing = "organizing"
    collective_bargaining = "collective_bargaining"
    wage_scheduling = "wage_scheduling"
    retaliation = "retaliation"
    whistleblowing = "whistleblowing"
    strike_conflict = "strike_conflict"
    works_council = "works_council"
    health_safety = "health_safety"


class Role(str, Enum):
    worker = "worker"
    manager = "manager"
    mediator = "mediator"


class Jurisdiction(str, Enum):
    US = "US"
    UK = "UK"
    DE = "DE"
    unknown = "unknown"


class Language(str, Enum):
    en = "en"
    de = "de"


class Difficulty(str, Enum):
    easy = "easy"
    medium = "medium"
    hard = "hard"


class AxisPole(str, Enum):
    """Expected direction for gold axis targets (not an exact score)."""
    low = "low"       # solidarity / collective / rights-aware / actionable pole
    neutral = "neutral"
    high = "high"     # confrontative / individual / rights-blind / vague pole


class Source(str, Enum):
    manual = "manual"
    llm_draft = "llm_draft"
    adapted_from_case = "adapted_from_case"


class ReviewStatus(str, Enum):
    unreviewed = "unreviewed"
    reviewed = "reviewed"
    approved = "approved"
    rejected = "rejected"


class RefusalClass(str, Enum):
    appropriate_refusal = "appropriate_refusal"
    safe_completion = "safe_completion"
    full_compliance = "full_compliance"
    harmful_compliance = "harmful_compliance"
    unclear = "unclear"


# ── Gold Axis Targets (sub-model) ───────────────────────────────────────────

class GoldAxisTargets(BaseModel):
    """Expected pole direction; used for coverage tracking, not scoring."""
    solidarity: Optional[AxisPole] = None
    collectivism: Optional[AxisPole] = None
    rights_awareness: Optional[AxisPole] = None
    actionability: Optional[AxisPole] = None


# ── 1. Scenario Schema ──────────────────────────────────────────────────────

class Scenario(BaseModel):
    scenario_id: str = Field(..., pattern=r"^S\d{3,4}$", description="e.g. S001, S0042")
    domain: Domain
    subdomain: Optional[str] = Field(None, description="Finer tag for coverage tracking")
    role_prompt: Role
    jurisdiction_context: Jurisdiction
    language: Language = Language.en
    difficulty: Difficulty = Difficulty.medium
    ambiguity_flag: bool = Field(False, description="True if scenario has deliberately ambiguous facts")
    refusal_trap: bool = Field(False, description="True if prompt asks for harmful/illegal assistance")
    user_goal: str = Field(..., min_length=10, description="The user message sent to the LLM")
    system_prompt: Optional[str] = Field(None, description="Optional system prompt for role-based testing")
    gold_risks: list[str] = Field(..., min_length=1, description="Risks a naive response might exhibit")
    gold_minimum_points: list[str] = Field(..., min_length=1, description="Things a good response MUST include")
    gold_axis_targets: Optional[GoldAxisTargets] = None
    source: Source = Source.manual
    review_status: ReviewStatus = ReviewStatus.unreviewed
    notes: str = ""

    @field_validator("scenario_id")
    @classmethod
    def scenario_id_format(cls, v: str) -> str:
        if not v.startswith("S"):
            raise ValueError("scenario_id must start with 'S'")
        return v


# ── 2. Model Output Schema ──────────────────────────────────────────────────

class ModelOutput(BaseModel):
    run_id: str = Field(..., description="Unique run identifier")
    model_name: str = Field(..., description="e.g. gpt-4o, claude-3.5-sonnet")
    model_version: Optional[str] = None
    decoding_config: dict = Field(default_factory=dict, description="temperature, top_p, etc.")
    scenario_id: str = Field(..., pattern=r"^S\d{3,4}$")
    raw_response: str = Field(..., min_length=1)
    timestamp: str = Field(..., description="ISO-8601 UTC timestamp")
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    latency_ms: Optional[float] = None


# ── 3. Annotation Schema ────────────────────────────────────────────────────

class Annotation(BaseModel):
    scenario_id: str = Field(..., pattern=r"^S\d{3,4}$")
    model_name: str
    rater_id: str = Field(..., description="Human rater or AI-judge identifier")
    solidarity_score: int = Field(..., ge=1, le=5)
    collectivism_score: int = Field(..., ge=1, le=5)
    rights_awareness_score: int = Field(..., ge=1, le=5)
    actionability_score: int = Field(..., ge=1, le=5)
    refusal_class: RefusalClass
    notes: str = ""
