"""Fetch DIVA101 streaming responses for the legal-QA benchmark.

Calls the GWDG `chat-ai.academiccloud.de` endpoint with the SAIA gateway
header + streaming + an Arcana ID — the only combination that actually
invokes RAG retrieval (see `Agent-ClaudeCode/mistakes.md` 2026-04-29 for
why; the matrix bypassed Arcana for two weeks because any of those three
ingredients was missing).

Writes one `DivaResponse` JSONL per (SUT × RAG tier). The companion
`diva_playback` solver replays these into Inspect-AI for grading.

Usage:
    # Single (SUT × tier × all questions) shot:
    python scripts/diva_fetch.py \\
        --sut openai-api/gwdg/qwen3.5-397b-a17b \\
        --arcana-id ananyapam.de01/Betriebsverfassungsgesetz \\
        --rag-label "Öff. Mat." \\
        --out data/diva_responses/qwen397b_oeffmat.jsonl

    # Smoke (1 question only):
    python scripts/diva_fetch.py ... --limit 1

    # Resume a partial run (skips question_ids already present):
    python scripts/diva_fetch.py ... --out path/with/partial.jsonl

Env (.env):
    GWDG_API_KEY, GWDG_BASE_URL  — required
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")

from openai import AsyncOpenAI, APIError

from inspect_benchmark import DIVA101_SYSTEM_PROMPT, QUESTIONS_PATH
from schema import DivaResponse


# ── Config ──────────────────────────────────────────────────────────────────

# DIVA's decoding settings — must match `inspect_benchmark.SUT_DECODING`.
DECODING = {"temperature": 0.0, "top_p": 0.05}

# SAIA gateway header — without this, requests bypass Arcana and hit raw vLLM.
SAIA_HEADER = {"inference-service": "saia-openai-gateway"}

# Streaming overall timeout (per call). Arcana retrieval + reasoning preamble
# can take 30–50s; 600s leaves headroom for slow tiers + cold starts.
STREAM_TIMEOUT_S = 600.0

# Default output dir. Path convention: <sut_slug>__<rag_slug>.jsonl
DEFAULT_OUT_DIR = REPO_ROOT / "data" / "diva_responses"

# `[RREF12] BetrVG-Komm-Fitting.pdf p.45,3:7 (0.82)` — captures all such tokens
# verbatim from streamed content. Per the GWDG SAIA contract, retrieval refs
# are inlined in `content`, not in `annotations` or `tool_calls`.
RREF_RE = re.compile(r"\[RREF\d+\][^\[\n]*?\([0-9.]+\)")


# ── Helpers ─────────────────────────────────────────────────────────────────


def _strip_service_prefix(model: str) -> str:
    """`openai-api/gwdg/qwen3.5-397b-a17b` → `qwen3.5-397b-a17b`."""
    return model.rsplit("/", 1)[-1]


def _slug(s: str) -> str:
    """Filesystem-safe slug for path construction."""
    return re.sub(r"[^\w.-]+", "-", s).strip("-").lower()


def _load_questions(path: Path, ids: list[str] | None = None, limit: int | None = None) -> list[dict]:
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if ids is not None and rec.get("question_id") not in ids:
            continue
        rows.append(rec)
    if limit is not None:
        rows = rows[:limit]
    return rows


def _existing_ids(out_path: Path) -> set[str]:
    """Question IDs with a *successful* row in `out_path` — for resumability.

    Errored rows are intentionally NOT counted: a rerun must retry them.
    Multiple rows for the same question_id can coexist in the JSONL after
    a retry succeeds — the playback solver builds a dict keyed on
    question_id (last-write-wins), so the latest successful row prevails.
    """
    if not out_path.exists():
        return set()
    success: dict[str, bool] = {}  # qid -> any-row-succeeded
    for line in out_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        qid = rec.get("question_id")
        if not qid:
            continue
        if not rec.get("error") and rec.get("raw_response"):
            success[qid] = True
    return {qid for qid, ok in success.items() if ok}


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _append_jsonl(path: Path, response: DivaResponse) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(response.model_dump_json() + "\n")


# ── Streaming call ──────────────────────────────────────────────────────────


async def _fetch_one(
    client: AsyncOpenAI,
    sut_short: str,
    arcana_id: str,
    rag_label: str,
    question: dict,
) -> DivaResponse:
    """Stream a single (model × tier × question) call. Catches errors into the row."""
    qid = question["question_id"]
    user_text = question["question_text"]

    started = time.monotonic()
    fetched_at = _now_iso()
    chunks: list[str] = []
    finish_reason: str | None = None
    error: str | None = None

    try:
        stream = await client.chat.completions.create(
            model=sut_short,
            messages=[
                {"role": "system", "content": DIVA101_SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ],
            stream=True,
            extra_headers=SAIA_HEADER,
            extra_body={"arcana": {"id": arcana_id}},
            timeout=STREAM_TIMEOUT_S,
            **DECODING,
        )
        async for chunk in stream:
            # SAIA gateway emits non-standard error frames as
            # `type='error'` with `choices=None`; the OpenAI SDK
            # passes them through. Without this branch they look
            # identical to "stream ended with no content."
            if getattr(chunk, "type", None) == "error":
                error = (
                    f"SAIA stream error (status={getattr(chunk, 'status', '?')}): "
                    f"{getattr(chunk, 'message', repr(chunk))}"
                )
                break
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            delta = choice.delta
            if delta is not None and getattr(delta, "content", None):
                chunks.append(delta.content)
            if choice.finish_reason is not None:
                finish_reason = choice.finish_reason
    except APIError as e:
        error = f"{type(e).__name__}: {e}"
    except Exception as e:  # network / cancel / decode etc.
        error = f"{type(e).__name__}: {e}"

    # Stream that opened, returned no content, and closed cleanly is a silent
    # failure (e.g. some gateway misconfigurations). Mark it as such.
    if error is None and not chunks:
        error = "stream returned 0 content chunks (silent no-op)"

    elapsed = time.monotonic() - started
    raw = "".join(chunks)
    rrefs = RREF_RE.findall(raw)

    return DivaResponse(
        question_id=qid,
        sut_model=sut_short,
        rag_label=rag_label,
        arcana_id=arcana_id,
        raw_response=raw,
        rref_markers=rrefs,
        finish_reason=finish_reason,
        fetched_at=fetched_at,
        elapsed_s=round(elapsed, 3),
        error=error,
    )


# Failure modes worth retrying once before giving up. ReadTimeout is excluded
# (each retry costs another ~600s — better to let the orchestrator-level rerun
# decide whether to re-attempt).
_RETRIABLE_PATTERNS = (
    "APIConnectionError",
    "stream returned 0 content chunks",
)


async def _fetch_one_with_retry(
    client: AsyncOpenAI,
    sut_short: str,
    arcana_id: str,
    rag_label: str,
    question: dict,
    max_retries: int = 1,
) -> DivaResponse:
    """`_fetch_one` + one retry on the two cheap transient failure modes."""
    response = await _fetch_one(client, sut_short, arcana_id, rag_label, question)
    attempts = 0
    while (
        response.error
        and attempts < max_retries
        and any(p in response.error for p in _RETRIABLE_PATTERNS)
    ):
        attempts += 1
        delay = 5.0 if "APIConnectionError" in response.error else 1.0
        print(f"  [retry {attempts}/{max_retries}] {question['question_id']}: "
              f"{response.error[:80]} — sleeping {delay:.0f}s", flush=True)
        await asyncio.sleep(delay)
        response = await _fetch_one(client, sut_short, arcana_id, rag_label, question)
    return response


# ── Runner ──────────────────────────────────────────────────────────────────


async def fetch_run(
    sut: str,
    arcana_id: str,
    rag_label: str,
    out_path: Path,
    questions: Iterable[dict],
    concurrency: int = 4,
) -> tuple[int, int, int]:
    """Fetch (SUT × tier × questions) and append rows to `out_path`. Idempotent.

    Streams up to `concurrency` requests in flight at once. Each completed row
    is appended under an asyncio.Lock — DivaResponse JSONL lines exceed POSIX's
    PIPE_BUF atomic-write threshold, so concurrent appends without a lock would
    risk interleaved bytes mid-line.

    Progress is printed as workers complete (which may be out of input order);
    the printed `n_done/total` reflects completion order, not input position.

    Returns (n_attempted, n_success, n_error). `n_attempted` excludes
    question_ids already present in `out_path` from a prior run.
    """
    api_key = os.environ.get("GWDG_API_KEY")
    base_url = os.environ.get("GWDG_BASE_URL")
    if not api_key or not base_url:
        raise SystemExit("ERROR: GWDG_API_KEY and GWDG_BASE_URL must be set in .env")

    sut_short = _strip_service_prefix(sut)
    skip = _existing_ids(out_path)

    pending = [q for q in questions if q["question_id"] not in skip]
    n_skipped = sum(1 for q in questions if q["question_id"] in skip)
    if n_skipped:
        print(f"  [resume] skipping {n_skipped} already-fetched question(s) in {out_path.name}")

    if not pending:
        return 0, 0, 0

    sem = asyncio.Semaphore(max(1, concurrency))
    write_lock = asyncio.Lock()
    n_ok = 0
    n_err = 0
    n_done = 0
    total = len(pending)

    if concurrency > 1:
        print(f"  [concurrency={concurrency}] {total} fetches in flight (max)")

    async with AsyncOpenAI(api_key=api_key, base_url=base_url) as client:
        async def worker(q: dict) -> None:
            nonlocal n_ok, n_err, n_done
            async with sem:
                response = await _fetch_one_with_retry(
                    client, sut_short, arcana_id, rag_label, q
                )
            async with write_lock:
                _append_jsonl(out_path, response)
                n_done += 1
                qid = q["question_id"]
                if response.error:
                    n_err += 1
                    print(f"  [{n_done:>2}/{total}] {qid} ERROR "
                          f"({response.elapsed_s:.1f}s): {response.error[:120]}")
                else:
                    n_ok += 1
                    print(f"  [{n_done:>2}/{total}] {qid} ok "
                          f"({response.elapsed_s:.1f}s, "
                          f"{len(response.raw_response)} chars, "
                          f"{len(response.rref_markers)} RREFs)")

        await asyncio.gather(*(worker(q) for q in pending))

    return total, n_ok, n_err


def resolve_out_path(arg: str | None, sut: str, rag_label: str) -> Path:
    """Construct (or honour) the JSONL path for a (SUT × RAG) fetch run."""
    if arg:
        return Path(arg).expanduser().resolve()
    sut_slug = _slug(_strip_service_prefix(sut))
    rag_slug = _slug(rag_label)
    return DEFAULT_OUT_DIR / f"{sut_slug}__{rag_slug}.jsonl"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--sut", required=True,
                        help="SUT model id (e.g. openai-api/gwdg/qwen3.5-397b-a17b or just qwen3.5-397b-a17b)")
    parser.add_argument("--arcana-id", required=True,
                        help="Arcana RAG id (e.g. ananyapam.de01/Betriebsverfassungsgesetz)")
    parser.add_argument("--rag-label", required=True,
                        help="Human label for this tier (e.g. 'Öff. Mat.')")
    parser.add_argument("--out", default=None,
                        help=f"Output JSONL path (default: {DEFAULT_OUT_DIR.relative_to(REPO_ROOT)}/<sut>__<rag>.jsonl)")
    parser.add_argument("--questions", default=str(QUESTIONS_PATH),
                        help=f"Questions JSONL (default: {QUESTIONS_PATH.relative_to(REPO_ROOT)})")
    parser.add_argument("--limit", type=int, default=None,
                        help="Fetch only the first N questions (smoke test)")
    parser.add_argument("--only", default=None,
                        help="Comma-separated question_ids to fetch (e.g. Q-P1-CZ-01,Q-P1-CZ-02)")
    parser.add_argument("--concurrency", type=int, default=4,
                        help="Max concurrent in-flight streams (default: 4). "
                             "Set to 1 for fully sequential.")
    args = parser.parse_args()

    out_path = resolve_out_path(args.out, args.sut, args.rag_label)
    ids = [s.strip() for s in args.only.split(",")] if args.only else None
    questions = _load_questions(Path(args.questions), ids=ids, limit=args.limit)

    if not questions:
        print("ERROR: no questions matched the filters.", file=sys.stderr)
        return 2

    print(f"DIVA fetch")
    print(f"  SUT:       {args.sut}")
    print(f"  RAG:       {args.rag_label}  ({args.arcana_id})")
    print(f"  Questions: {len(questions)} from {args.questions}")
    print(f"  Output:    {out_path}")
    print()

    t0 = time.monotonic()
    n_attempted, n_ok, n_err = asyncio.run(
        fetch_run(args.sut, args.arcana_id, args.rag_label, out_path, questions,
                  concurrency=args.concurrency)
    )
    elapsed = time.monotonic() - t0

    print()
    print(f"Done in {elapsed:.1f}s. {n_ok}/{n_attempted} succeeded, {n_err} errored.")
    return 0 if n_err == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
