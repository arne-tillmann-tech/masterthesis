"""
Ingest Phase 1+2 TESTFRAGEN from Testung1DIVA.zip into JSONL records.

Phase 1 docs (with expert reference answers) land in
data/legal_qa/questions_with_reference.jsonl. Phase 2 docs (Frage + Systempromt
only, reference still pending) land in
data/legal_qa/questions_pending_reference.jsonl. The manual evaluation grid
(model output × material level) is preserved on every record.

Usage:
    python scripts/ingest_testfragen.py
    python scripts/ingest_testfragen.py --source data/Testung1DIVA.zip --strict
    python scripts/ingest_testfragen.py --extract-to data/legal_qa/raw/

The default --source and --out-dir resolve relative to the repo root, so the
script can be invoked from any working directory.
"""

from __future__ import annotations

import argparse
import io
import re
import sys
import zipfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterator, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from docx import Document
from docx.document import Document as DocxDocument
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph
from pydantic import ValidationError

from legal_qa_schema import ModelEvaluation, Question


DEFAULT_SOURCE = REPO_ROOT / "data" / "Testung1DIVA.zip"
DEFAULT_OUT_DIR = REPO_ROOT / "data" / "legal_qa"

FILENAME_RE = re.compile(r"^TESTFRAGE_(\d+)_([A-Z]{2})_Phase_([12])(?!\d)")

QUESTION_ANCHOR_RE = re.compile(r"^frage\s*/?\s*pro?mp?t\s*[:.]", re.IGNORECASE)
EXPECTED_ANCHOR_RE = re.compile(r"^erwartete\s+antwort\s*[:.]?", re.IGNORECASE)
SYSTEMPROMPT_ANCHOR_RE = re.compile(r"^system\s*pro?mp?t\s*[:.]", re.IGNORECASE)
ANSWER_HEADER_RE = re.compile(r"^antwort\b", re.IGNORECASE)

# Annotator attribution markers like "[von Christina]" — leak reviewer's first name.
ANNOTATOR_NOTE_RE = re.compile(
    r"\[von\s+[A-ZÄÖÜ][\wäöüß]*(?:\s+[A-ZÄÖÜ][\wäöüß]*)?\]"
)
# Known author full-name → initials mapping (extend if more leak through review).
NAME_REDACTIONS: dict[str, str] = {
    "Christina": "CZ",
}


# ── Text + docx helpers ──────────────────────────────────────────────────────


def normalize(text: str) -> str:
    """Normalize unicode, collapse whitespace, redact reviewer first names."""
    if not text:
        return ""
    text = (
        text.replace("„", '"').replace("“", '"').replace("”", '"')
        .replace("–", "-").replace("—", "-")
        .replace(" ", " ").replace("\xa0", " ")
    )
    text = re.sub(r"[ \t]+", " ", text)
    text = ANNOTATOR_NOTE_RE.sub("[reviewer]", text)
    for full, initials in NAME_REDACTIONS.items():
        text = re.sub(rf"\b{re.escape(full)}\b", initials, text)
    return text.strip()


def iter_block_items(doc: DocxDocument) -> Iterator[Paragraph | Table]:
    """Yield body-level paragraphs and tables in document order."""
    body = doc.element.body
    for child in body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, doc)
        elif child.tag == qn("w:tbl"):
            yield Table(child, doc)


def is_bullet_paragraph(p: Paragraph) -> bool:
    pPr = p._element.find(qn("w:pPr"))
    if pPr is None:
        return False
    return pPr.find(qn("w:numPr")) is not None


# ── Table parsing ────────────────────────────────────────────────────────────


def parse_table(table: Table, table_index: int) -> list[ModelEvaluation]:
    """Convert one evaluation table into ModelEvaluation rows (one per data column).

    Header row gives material levels (skipping leftmost label column). Data rows
    are matched by their first cell (Antwort / Zeit / Referenz / Bewertung /
    Testung 2. Person …). Empty columns are dropped.
    """
    rows = [[normalize(cell.text) for cell in row.cells] for row in table.rows]
    if len(rows) < 2 or len(rows[0]) < 2:
        return []

    material_levels = rows[0][1:]
    rows_by_field: dict[str, list[str]] = {}
    for row in rows[1:]:
        if not row:
            continue
        label = row[0].lower()
        cells = row[1:]
        if "differenz" in label or "2. person" in label:
            rows_by_field["second_person_diff"] = cells
        elif label.startswith("antwort"):
            rows_by_field["answer"] = cells
        elif "zeit" in label:
            rows_by_field["response_time"] = cells
        elif "referenz" in label:
            rows_by_field["references_cited"] = cells
        elif "bewertung" in label:
            rows_by_field["human_evaluation"] = cells

    evals: list[ModelEvaluation] = []
    for col_idx, level in enumerate(material_levels):
        if not level:
            continue

        def cell(field: str) -> Optional[str]:
            cells = rows_by_field.get(field, [])
            if col_idx < len(cells):
                return cells[col_idx] or None
            return None

        ev = ModelEvaluation(
            table_index=table_index,
            material_level=level,
            answer=cell("answer"),
            response_time=cell("response_time"),
            references_cited=cell("references_cited"),
            human_evaluation=cell("human_evaluation"),
            second_person_diff=cell("second_person_diff"),
        )
        if any([
            ev.answer, ev.response_time, ev.references_cited,
            ev.human_evaluation, ev.second_person_diff,
        ]):
            evals.append(ev)
    return evals


# ── Document parsing ─────────────────────────────────────────────────────────


@dataclass
class ParsedDoc:
    question_text: str
    system_prompt: Optional[str]
    reference_answer: Optional[str]
    reference_bullets: Optional[list[str]]
    model_evaluations: list[ModelEvaluation]


def parse_body(doc: DocxDocument) -> ParsedDoc:
    question_text: Optional[str] = None
    system_prompt_lines: list[str] = []
    reference_answer_lines: list[str] = []
    reference_bullets: list[str] = []
    model_evaluations: list[ModelEvaluation] = []

    section: Optional[str] = None  # 'expected' | 'systempromt' | None
    awaiting_question = False
    table_counter = 0

    for blk in iter_block_items(doc):
        if isinstance(blk, Table):
            table_counter += 1
            section = None
            model_evaluations.extend(parse_table(blk, table_counter))
            continue

        text = normalize(blk.text)
        if not text:
            continue

        if QUESTION_ANCHOR_RE.match(text):
            section = None
            after = QUESTION_ANCHOR_RE.sub("", text, count=1).strip()
            if after:
                question_text = after
            else:
                awaiting_question = True
            continue

        if awaiting_question:
            question_text = text
            awaiting_question = False
            continue

        if EXPECTED_ANCHOR_RE.match(text):
            section = "expected"
            after = EXPECTED_ANCHOR_RE.sub("", text, count=1).strip()
            if after:
                if is_bullet_paragraph(blk):
                    reference_bullets.append(after)
                else:
                    reference_answer_lines.append(after)
            continue

        if SYSTEMPROMPT_ANCHOR_RE.match(text):
            section = "systempromt"
            after = SYSTEMPROMPT_ANCHOR_RE.sub("", text, count=1).strip()
            if after:
                system_prompt_lines.append(after)
            continue

        if ANSWER_HEADER_RE.match(text):
            # "Antwort ChatGPT (5.1)" — model-output prose follows; close any prose section.
            section = None
            continue

        if section == "expected":
            if is_bullet_paragraph(blk):
                reference_bullets.append(text)
            else:
                reference_answer_lines.append(text)
        elif section == "systempromt":
            system_prompt_lines.append(text)

    if not question_text:
        raise ValueError("No question text found")

    return ParsedDoc(
        question_text=question_text,
        system_prompt="\n".join(system_prompt_lines).strip() or None,
        reference_answer="\n".join(reference_answer_lines).strip() or None,
        reference_bullets=reference_bullets or None,
        model_evaluations=model_evaluations,
    )


def build_question(blob: bytes, filename: str) -> Question:
    base = filename.rsplit("/", 1)[-1]
    m = FILENAME_RE.match(base)
    if not m:
        raise ValueError(f"Filename does not match TESTFRAGE pattern: {base!r}")
    number = int(m.group(1))
    initials = m.group(2)
    phase = int(m.group(3))

    parsed = parse_body(Document(io.BytesIO(blob)))

    has_reference = bool(parsed.reference_answer or parsed.reference_bullets)
    if phase == 1 and not has_reference:
        raise ValueError(f"Phase 1 doc {base!r} has no reference answer (parse failure?)")
    if phase == 2 and has_reference:
        raise ValueError(f"Phase 2 doc {base!r} unexpectedly has a reference answer")

    return Question(
        question_id=f"Q-P{phase}-{initials}-{number:02d}",
        phase=phase,
        author_initials=initials,
        question_number=number,
        language="de",
        question_text=parsed.question_text,
        system_prompt=parsed.system_prompt,
        reference_answer=parsed.reference_answer,
        reference_bullets=parsed.reference_bullets,
        model_evaluations=parsed.model_evaluations,
        source_docx=base,
        extracted_at=date.today().isoformat(),
        subtask_tag=None,
        needs_reference=(phase == 2),
        review_status="unreviewed",
    )


# ── Zip walking + dedup ──────────────────────────────────────────────────────


@dataclass
class ZipEntry:
    full_name: str
    base: str
    phase: int
    number: int
    is_aktuell: bool


def collect_entries(zip_path: Path) -> list[ZipEntry]:
    entries: dict[tuple[int, int], ZipEntry] = {}
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            base = info.filename.rsplit("/", 1)[-1]
            if not base.lower().endswith(".docx"):
                continue
            if not base.startswith("TESTFRAGE_"):
                continue
            if "_Blanco" in base or "Nummerierung" in base:
                continue
            m = FILENAME_RE.match(base)
            if not m:
                continue
            number = int(m.group(1))
            phase = int(m.group(3))
            is_aktuell = "aktuell" in base.lower()
            entry = ZipEntry(
                full_name=info.filename,
                base=base,
                phase=phase,
                number=number,
                is_aktuell=is_aktuell,
            )
            key = (phase, number)
            existing = entries.get(key)
            if existing is None or (is_aktuell and not existing.is_aktuell):
                entries[key] = entry
    return sorted(entries.values(), key=lambda e: (e.phase, e.number))


# ── Main pipeline ────────────────────────────────────────────────────────────


def write_jsonl(records: list[Question], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for q in records:
            f.write(q.model_dump_json() + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE,
                        help="Path to Testung1DIVA.zip (default: data/Testung1DIVA.zip)")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR,
                        help="Directory for the two JSONL outputs (default: data/legal_qa/)")
    parser.add_argument("--extract-to", type=Path, default=None,
                        help="Optional: also extract raw .docx files here for debugging")
    parser.add_argument("--strict", action="store_true",
                        help="Fail on first parse/validation error (default: log and continue)")
    args = parser.parse_args()

    if not args.source.exists():
        print(f"ERROR: source zip not found: {args.source}", file=sys.stderr)
        return 1

    entries = collect_entries(args.source)
    print(f"Found {len(entries)} TESTFRAGE candidates after dedup ({args.source.name})")

    phase1: list[Question] = []
    phase2: list[Question] = []
    errors: list[tuple[str, str]] = []

    with zipfile.ZipFile(args.source) as z:
        for entry in entries:
            blob = z.read(entry.full_name)
            if args.extract_to is not None:
                args.extract_to.mkdir(parents=True, exist_ok=True)
                (args.extract_to / entry.base).write_bytes(blob)
            try:
                q = build_question(blob, entry.full_name)
            except (ValueError, ValidationError) as e:
                msg = f"{entry.base}: {e}"
                errors.append((entry.base, str(e)))
                if args.strict:
                    print(f"ERROR (strict): {msg}", file=sys.stderr)
                    return 2
                print(f"  ✗ {msg}")
                continue
            (phase1 if q.phase == 1 else phase2).append(q)
            print(f"  ✓ {entry.base} → {q.question_id}")

    p1_path = args.out_dir / "questions_with_reference.jsonl"
    p2_path = args.out_dir / "questions_pending_reference.jsonl"
    write_jsonl(phase1, p1_path)
    write_jsonl(phase2, p2_path)

    print()
    print(f"Phase 1 records: {len(phase1)} → {p1_path.relative_to(REPO_ROOT)}")
    print(f"Phase 2 records: {len(phase2)} → {p2_path.relative_to(REPO_ROOT)}")
    if errors:
        print(f"\n⚠ {len(errors)} errors:")
        for name, err in errors:
            print(f"  {name}: {err[:200]}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
