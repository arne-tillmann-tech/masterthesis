"""Local OpenAI-compatible proxy that exposes GitHub Copilot's chat API.

Why: Copilot's chat-completions endpoint speaks OpenAI's wire format but adds
two complications that Inspect-AI's `openai-api` provider can't handle out of
the box: (a) a 2-step OAuth → short-lived bearer (~30 min) auth flow, and (b)
mandatory streaming with custom IDE headers. This proxy hides both behind a
vanilla `POST /v1/chat/completions` listener, so Inspect sees a plain
OpenAI-compatible service.

How it's wired: in .env, set
    COPILOT_OAUTH=ghu_…              (long-lived OAuth — secret)
    COPILOT_API_KEY=unused-placeholder
    COPILOT_BASE_URL=http://localhost:8765/v1
    COPILOT_PROXY_PORT=8765
then start this proxy in the background and run an Inspect eval with
`--model openai-api/copilot/claude-sonnet-4.5` (or any other Copilot model).

Usage:
    python scripts/_copilot_proxy.py
    python scripts/_copilot_proxy.py --port 8765 --verbose

Concurrency: served by ThreadingHTTPServer, one thread per inbound request.
The bearer cache is shared and protected by a Lock so concurrent refreshes
collapse into one upstream mint.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")


# ── Upstream constants ───────────────────────────────────────────────────────

COPILOT_TOKEN_URL = "https://api.github.com/copilot_internal/v2/token"
COPILOT_CHAT_URL = "https://api.individual.githubcopilot.com/chat/completions"
COPILOT_MODELS_URL = "https://api.individual.githubcopilot.com/models"

IDE_HEADERS = {
    "Editor-Version": "vscode/1.96.2",
    "User-Agent": "GitHubCopilotChat/0.26.7",
    "X-Github-Api-Version": "2025-04-01",
    "Accept": "application/json",
}

# Refresh the bearer when fewer than this many seconds remain on it.
BEARER_REFRESH_MARGIN_S = 90

VERBOSE = False


# ── Bearer cache ────────────────────────────────────────────────────────────


class BearerCache:
    """Thread-safe holder for the short-lived Copilot bearer token."""

    def __init__(self, oauth: str):
        self._oauth = oauth
        self._lock = threading.Lock()
        self._token: Optional[str] = None
        self._expires_at: float = 0.0  # unix seconds

    def get(self) -> str:
        with self._lock:
            now = time.time()
            if self._token is None or (self._expires_at - now) < BEARER_REFRESH_MARGIN_S:
                self._refresh_locked()
            return self._token  # type: ignore[return-value]

    def _refresh_locked(self) -> None:
        req = urllib.request.Request(
            COPILOT_TOKEN_URL,
            headers={"Authorization": f"Bearer {self._oauth}", **IDE_HEADERS},
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            payload = json.load(r)
        self._token = payload["token"]
        self._expires_at = float(payload.get("expires_at", time.time() + 1500))
        if VERBOSE:
            ttl = int(self._expires_at - time.time())
            print(f"[proxy] refreshed bearer (ttl={ttl}s)", flush=True)


# ── Stream handling ─────────────────────────────────────────────────────────


def _iter_sse_lines(resp):
    """Yield raw SSE lines from an upstream urllib response."""
    buf = b""
    for chunk in resp:
        buf += chunk
        while b"\n" in buf:
            line, _, buf = buf.partition(b"\n")
            yield line
    if buf:
        yield buf


def _accumulate_sse(resp) -> dict:
    """Consume an SSE stream and assemble it into a single chat-completion dict."""
    content_parts: list[str] = []
    finish_reason: Optional[str] = None
    model: Optional[str] = None
    last_id: Optional[str] = None
    usage: Optional[dict] = None
    role = "assistant"

    for raw in _iter_sse_lines(resp):
        line = raw.decode("utf-8", errors="replace").rstrip("\r")
        if not line.startswith("data: "):
            continue
        payload = line[6:]
        if payload.strip() == "[DONE]":
            break
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if "id" in event:
            last_id = event["id"]
        if "model" in event:
            model = event["model"]
        for choice in event.get("choices", []):
            delta = choice.get("delta") or {}
            piece = delta.get("content")
            if piece:
                content_parts.append(piece)
            if delta.get("role"):
                role = delta["role"]
            if choice.get("finish_reason"):
                finish_reason = choice["finish_reason"]
        if event.get("usage"):
            usage = event["usage"]

    return {
        "id": last_id or f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model or "unknown",
        "choices": [
            {
                "index": 0,
                "message": {"role": role, "content": "".join(content_parts)},
                "finish_reason": finish_reason or "stop",
            }
        ],
        "usage": usage or {},
    }


# ── HTTP handler ────────────────────────────────────────────────────────────


class CopilotProxyHandler(BaseHTTPRequestHandler):
    bearer_cache: BearerCache  # set on the class by main()

    # Silence the default per-request access log; we have our own VERBOSE knob.
    def log_message(self, format: str, *args) -> None:  # noqa: A002
        if VERBOSE:
            super().log_message(format, *args)

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status: int, message: str) -> None:
        self._send_json(status, {"error": {"message": message, "type": "proxy_error"}})

    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/v1/models", "/models"):
            try:
                bearer = self.bearer_cache.get()
                req = urllib.request.Request(
                    COPILOT_MODELS_URL,
                    headers={"Authorization": f"Bearer {bearer}", **IDE_HEADERS},
                )
                with urllib.request.urlopen(req, timeout=30) as r:
                    body = r.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self._send_error(502, f"upstream models error: {e}")
            return

        if self.path in ("/", "/health"):
            self._send_json(200, {"status": "ok"})
            return

        self._send_error(404, f"unhandled path: {self.path}")

    def do_POST(self) -> None:  # noqa: N802
        if self.path not in ("/v1/chat/completions", "/chat/completions"):
            self._send_error(404, f"unhandled path: {self.path}")
            return

        length = int(self.headers.get("Content-Length", "0"))
        try:
            body_bytes = self.rfile.read(length) if length > 0 else b"{}"
            request_body = json.loads(body_bytes)
        except (ValueError, json.JSONDecodeError) as e:
            self._send_error(400, f"invalid JSON body: {e}")
            return

        inbound_stream = bool(request_body.get("stream", False))
        # Copilot rejects stream=False — always upstream-stream, then collapse if needed.
        request_body["stream"] = True
        upstream_body = json.dumps(request_body).encode()

        try:
            bearer = self.bearer_cache.get()
        except Exception as e:
            self._send_error(502, f"bearer mint failed: {e}")
            return

        upstream_headers = {
            "Authorization": f"Bearer {bearer}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "X-Initiator": "user",
            "Openai-Intent": "conversation-edits",
            "Editor-Version": IDE_HEADERS["Editor-Version"],
            "User-Agent": IDE_HEADERS["User-Agent"],
        }

        req = urllib.request.Request(
            COPILOT_CHAT_URL,
            data=upstream_body,
            headers=upstream_headers,
            method="POST",
        )

        try:
            upstream_resp = urllib.request.urlopen(req, timeout=300)
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")[:500]
            self._send_error(e.code, f"upstream {e.code}: {err_body}")
            return
        except Exception as e:
            self._send_error(502, f"upstream connection error: {e}")
            return

        if inbound_stream:
            # Pass-through SSE.
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            try:
                for raw in _iter_sse_lines(upstream_resp):
                    self.wfile.write(raw + b"\n")
                    self.wfile.flush()
            except Exception:
                pass  # client disconnect
            finally:
                upstream_resp.close()
            return

        # Non-streaming inbound: accumulate the SSE into a chat-completion dict.
        try:
            assembled = _accumulate_sse(upstream_resp)
        finally:
            upstream_resp.close()

        if VERBOSE:
            content_len = len(assembled["choices"][0]["message"]["content"])
            print(f"[proxy] {request_body.get('model')}: assembled {content_len} chars", flush=True)

        self._send_json(200, assembled)


# ── Entrypoint ──────────────────────────────────────────────────────────────


def main() -> int:
    global VERBOSE  # noqa: PLW0603

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--port", type=int,
                        default=int(os.environ.get("COPILOT_PROXY_PORT", "8765")))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    VERBOSE = args.verbose

    oauth = os.environ.get("COPILOT_OAUTH")
    if not oauth:
        print("ERROR: COPILOT_OAUTH not set in .env", file=sys.stderr)
        return 2

    cache = BearerCache(oauth)
    # Mint once eagerly so startup fails fast if the OAuth is bad.
    try:
        cache.get()
    except Exception as e:
        print(f"ERROR: failed to mint initial bearer: {e}", file=sys.stderr)
        return 3

    CopilotProxyHandler.bearer_cache = cache
    server = ThreadingHTTPServer((args.host, args.port), CopilotProxyHandler)
    print(f"[proxy] listening on http://{args.host}:{args.port}/v1/chat/completions", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[proxy] shutting down", flush=True)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
