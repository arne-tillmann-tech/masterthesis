"""
Inspect AI evaluation task for the legal-QA benchmark.

Loads Phase-1 TESTFRAGEN (questions with expert references) and grades each
model response with a 3-level LLM-as-judge verdict against the expert reference:
worse_than_reference | on_par_with_reference | better_than_reference.

The model under test runs with DIVA101's system prompt and decoding settings so
the external-frontier comparison is as apples-to-apples as possible (modulo
DIVA's RAG retrieval, which the frontier models do not have).

Usage (CLI):
    inspect eval inspect_benchmark.py --model openai/gpt-4o
    inspect eval inspect_benchmark.py --model openai/gpt-4o \\
        --model-role grader=anthropic/claude-sonnet-4-20250514
    inspect eval inspect_benchmark.py --model openai/gpt-4o --sample-id Q-P1-CZ-01

Environment variables (set in .env or shell):
    OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY  (as needed)
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from inspect_ai import Task, task
from inspect_ai.dataset import Sample, json_dataset
from inspect_ai.model import GenerateConfig, get_model
from inspect_ai.scorer import Score, Target, mean, scorer, stderr
from inspect_ai.solver import TaskState, generate, system_message


# ── Paths ────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent
QUESTIONS_PATH = REPO_ROOT / "data" / "legal_qa" / "questions_with_reference.jsonl"
JUDGE_PROMPT_PATH = REPO_ROOT / "judge_prompt.txt"


# ── DIVA101 system prompt and decoding (the SUT framing) ─────────────────────

# Verbatim from DIVA101 Wissensfinder. Frontier models receive the same prompt
# (without RAG retrieval — that asymmetry is acknowledged in the methodology).
DIVA101_SYSTEM_PROMPT = (
    "Sie sind ein Assistent für die Recherche und Abfrage von rechtlichen "
    "Dokumenten mit Zugriff auf eine aktuelle und umfassende Datenbank, die "
    "Gesetze, Vorschriften, Gerichtsentscheidungen, juristische Anträge und "
    "wissenschaftliche Kommentare rund um die Themen Betriebsrat und "
    "Gewerkschaft enthält. Ihre Aufgabe besteht darin, Benutzeranfragen mit "
    "größter Sorgfalt zu bearbeiten und sicherzustellen, dass alle Verweise "
    "auf Dokumente präzise, korrekt zitiert und inhaltlich relevant sind."
)

# DIVA's decoding settings — applied to the SUT for parity.
SUT_DECODING = GenerateConfig(temperature=0.0, top_p=0.05)


# ── Verdict labels ───────────────────────────────────────────────────────────

VERDICT_NUMERIC: dict[str, float] = {
    "worse_than_reference": 0.0,
    "on_par_with_reference": 1.0,
    "better_than_reference": 2.0,
}
VALID_VERDICTS = set(VERDICT_NUMERIC)
PASSING_VERDICTS = {"on_par_with_reference", "better_than_reference"}


# ── Dataset loader ───────────────────────────────────────────────────────────


def format_reference(
    reference_answer: str | None,
    reference_bullets: list[str] | None,
) -> str:
    """Build the expert reference string passed as Sample.target.

    Phase-1 records are bullets-only (14/18) or prose-only (4/18). Both are
    formatted into one text block; prose first, bullets second if both present.
    Raises if neither is provided (should never happen for the with_reference
    JSONL — the ingest validator already enforces this).
    """
    parts: list[str] = []
    if reference_answer and reference_answer.strip():
        parts.append(reference_answer.strip())
    if reference_bullets:
        bullets = "\n".join(f"- {b.strip()}" for b in reference_bullets if b.strip())
        if bullets:
            parts.append(bullets)
    if not parts:
        raise ValueError("Record has neither reference_answer nor reference_bullets")
    return "\n\n".join(parts)


def record_to_sample(record: dict) -> Sample:
    """Map a legal-QA JSONL record to an Inspect Sample.

    Maps:
      - question_text                                -> input
      - format_reference(answer, bullets)            -> target
      - question_id                                  -> id
      - phase / author / source_docx / subtask_tag   -> metadata
    """
    return Sample(
        input=record["question_text"],
        target=format_reference(
            record.get("reference_answer"),
            record.get("reference_bullets"),
        ),
        id=record["question_id"],
        metadata={
            "phase": record.get("phase"),
            "author_initials": record.get("author_initials"),
            "question_number": record.get("question_number"),
            "source_docx": record.get("source_docx"),
            "subtask_tag": record.get("subtask_tag"),
        },
    )


def load_questions() -> list[Sample]:
    """Load the Phase-1 (with_reference) corpus via Inspect's json_dataset."""
    return json_dataset(str(QUESTIONS_PATH), record_to_sample)


# ── Judge prompt ─────────────────────────────────────────────────────────────


def load_judge_prompt() -> str:
    return JUDGE_PROMPT_PATH.read_text(encoding="utf-8")


# ── Verdict scorer ───────────────────────────────────────────────────────────

VERDICT_RE = re.compile(
    r'"verdict"\s*:\s*"(worse_than_reference|on_par_with_reference|better_than_reference)"'
)


def _parse_verdict(completion: str) -> tuple[str | None, str]:
    """Extract verdict label + reasoning from a judge model output.

    Tolerates: leading/trailing markdown fences, surrounding text, and
    near-JSON output that fails strict json.loads. Returns (None, raw) if no
    valid verdict label can be recovered.
    """
    text = completion.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```\s*$", "", text)

    # Strict JSON first.
    try:
        data = json.loads(text)
        verdict = data.get("verdict")
        reasoning = data.get("reasoning", "") or ""
        if verdict in VALID_VERDICTS:
            return verdict, str(reasoning)
    except (json.JSONDecodeError, AttributeError):
        pass

    # Try to find a JSON object embedded in the text.
    obj_match = re.search(r"\{.*\}", text, re.DOTALL)
    if obj_match:
        try:
            data = json.loads(obj_match.group())
            verdict = data.get("verdict")
            reasoning = data.get("reasoning", "") or ""
            if verdict in VALID_VERDICTS:
                return verdict, str(reasoning)
        except (json.JSONDecodeError, AttributeError):
            pass

    # Last resort: regex-match the verdict line.
    m = VERDICT_RE.search(text)
    if m:
        return m.group(1), text

    return None, completion


@scorer(
    metrics={
        "verdict": [mean(), stderr()],
        "correct": [mean(), stderr()],
    }
)
def legal_qa_verdict_scorer(
    grader_model: str | None = None,
    temperature: float = 0.0,
):
    """Grade SUT responses against the expert reference using a 3-level verdict.

    Verdict labels: worse_than_reference | on_par_with_reference | better_than_reference.
    Numeric mapping for metrics: 0 / 1 / 2 (Score.value['verdict']).
    Derived 'correct' = 1.0 iff verdict in {on_par, better}, else 0.0.
    A judge output that cannot be parsed yields verdict = correct = -1.0
    (filter these in analysis; they should be rare with temperature=0).

    Args:
        grader_model: Model to use for grading. If None, uses the "grader"
                      model role (or falls back to the evaluated model).
        temperature: Temperature for the grader (default 0.0 for determinism).
    """
    judge_prompt = load_judge_prompt()

    async def score(state: TaskState, target: Target) -> Score:
        model = get_model(
            grader_model,
            role="grader",
            config=GenerateConfig(temperature=temperature),
        )

        prompt = judge_prompt.format(
            question=state.input_text,
            reference=target.text,
            model_response=state.output.completion,
        )

        result = await model.generate(prompt)
        verdict, reasoning = _parse_verdict(result.completion)

        if verdict is None:
            return Score(
                value={"verdict": -1.0, "correct": -1.0},
                explanation=f"Judge output could not be parsed:\n{result.completion}",
                metadata={"raw_judge_output": result.completion},
            )

        return Score(
            value={
                "verdict": VERDICT_NUMERIC[verdict],
                "correct": 1.0 if verdict in PASSING_VERDICTS else 0.0,
            },
            answer=state.output.completion[:500],
            explanation=reasoning,
            metadata={
                "verdict_label": verdict,
                "raw_judge_output": result.completion,
            },
        )

    return score


# ── Task definition ──────────────────────────────────────────────────────────


@task
def legal_qa_benchmark():
    """Evaluate frontier LLMs on legal-QA against expert references.

    Pipeline: DIVA101 system prompt → SUT generates → LLM-judge compares to
    expert reference → 3-level verdict (mapped 0/1/2) + binary `correct`.
    """
    return Task(
        dataset=load_questions(),
        solver=[
            system_message(DIVA101_SYSTEM_PROMPT),
            generate(),
        ],
        scorer=legal_qa_verdict_scorer(),
        config=SUT_DECODING,
    )
