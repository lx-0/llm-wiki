"""Single client for the local (or LAN) Ollama server.

Centralizes the gotchas documented in .ytstack/KNOWLEDGE.md:

- `format: "json"` is not enough — pass a full JSON Schema (with `enum` for
  non-empty strings) to `chat_schema`.
- Models still emit ```json fences sometimes; `parse_json_lenient` strips them
  and falls back to extracting the outermost {...} block.
- Native `/api/chat` is required for vision and constrained decoding;
  the OpenAI-compat `/v1/chat/completions` is fine for plain text.
- Temperature defaults follow the KNOWLEDGE.md notes: 0.0 for schema
  output (deterministic), 0.1 for everything else (avoid Ollama's prompt
  cache for identical inputs).

Base URL comes from `CONFIG.models.ollama_url`. Do NOT hardcode the IP.
"""

from __future__ import annotations

import json
import logging
import re
import socket
from typing import Any

import httpx

from .config import CONFIG
from .usage import LEDGER

_module_log = logging.getLogger(__name__)


_FENCE_LEADING = re.compile(r"^```[a-zA-Z]*\s*", flags=re.MULTILINE)
_FENCE_TRAILING = re.compile(r"\s*```\s*$", flags=re.MULTILINE)


# ── Connection hardening ──────────────────────────────────────────────
#
# TCP keepalive on every Ollama socket. The server is typically a LAN GPU
# box that sleeps / wakes / drops mid-request; when it goes away WITHOUT
# sending FIN/RST the local socket stays ESTABLISHED and a blocking recv()
# never returns. httpx's userspace read timeout did NOT break this — the
# review-wiki piggyback hung for 19h47m on one such half-open socket with
# `timeout=300` set (incident 2026-05-30, see KNOWLEDGE.md). Kernel-level
# keepalive probes detect the dead peer in ~_KEEPALIVE_IDLE + interval*count
# (≈120 s) and make recv() raise, independent of httpx timer behaviour.
#
# Built defensively: macOS exposes TCP_KEEPALIVE (idle), Linux TCP_KEEPIDLE.
# Interval/count are present on both but guarded via getattr just in case.
_KEEPALIVE_IDLE_S = 60       # idle seconds before the first probe
_KEEPALIVE_INTERVAL_S = 15   # seconds between probes
_KEEPALIVE_COUNT = 4         # peer declared dead after this many unacked probes
_WRITE_TIMEOUT_S = 30.0
_POOL_TIMEOUT_S = 10.0


def _keepalive_socket_options() -> list[tuple[int, int, int]]:
    """Socket options enabling TCP keepalive with bounded dead-peer detection.

    Passed to ``httpx.HTTPTransport(socket_options=...)``. Only includes
    options the running platform actually exposes, so it's a no-op-safe
    superset across macOS / Linux.
    """
    opts: list[tuple[int, int, int]] = [(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)]
    idle_opt = getattr(socket, "TCP_KEEPALIVE", None)
    if idle_opt is None:
        idle_opt = getattr(socket, "TCP_KEEPIDLE", None)  # Linux name
    if idle_opt is not None:
        opts.append((socket.IPPROTO_TCP, idle_opt, _KEEPALIVE_IDLE_S))
    intvl = getattr(socket, "TCP_KEEPINTVL", None)
    if intvl is not None:
        opts.append((socket.IPPROTO_TCP, intvl, _KEEPALIVE_INTERVAL_S))
    cnt = getattr(socket, "TCP_KEEPCNT", None)
    if cnt is not None:
        opts.append((socket.IPPROTO_TCP, cnt, _KEEPALIVE_COUNT))
    return opts


def _timeout(read_timeout: float) -> httpx.Timeout:
    """Explicit per-phase timeout. Connect is a short LAN-sane cap (config),
    read is the caller's budget, write/pool are engine constants. A single
    float would make connect == read, so a down host would burn the full read
    budget just failing to connect."""
    return httpx.Timeout(
        connect=float(CONFIG.limits.ollama_connect_timeout_s),
        read=read_timeout,
        write=_WRITE_TIMEOUT_S,
        pool=_POOL_TIMEOUT_S,
    )


def _client(read_timeout: float) -> httpx.Client:
    """httpx client with explicit phase timeouts + TCP keepalive transport.

    Every call site routes through this so the half-open-socket hardening is
    uniform. ``retries=0`` keeps a transient connect failure fast rather than
    silently retrying under the connect budget.
    """
    return httpx.Client(
        timeout=_timeout(read_timeout),
        transport=httpx.HTTPTransport(
            socket_options=_keepalive_socket_options(),
            retries=0,
        ),
    )


def _base_url() -> str:
    return CONFIG.models.ollama_url.rstrip("/")


# ── Liveness ──────────────────────────────────────────────────────────

def is_reachable(timeout: float = 5.0) -> bool:
    """Quick GET /api/tags. Used before kicking off long batches."""
    try:
        with _client(timeout) as c:
            r = c.get(f"{_base_url()}/api/tags")
        return r.status_code == 200
    except Exception as e:  # noqa: BLE001 — callers warn via warn_unreachable_once;
        # the exception detail (DNS vs refused vs timeout) is diagnostic only
        _module_log.debug("ollama reachability probe failed: %s: %s", type(e).__name__, e)
        return False


_UNREACHABLE_WARNED = False


def warn_unreachable_once(log, context: str = "") -> None:
    """Log the 'Ollama unreachable → skipping' notice at WARNING the first time
    this process hits it, DEBUG thereafter.

    An offline home GPU otherwise floods the log with a near-identical line per
    compiled file per pass (299 lines/48d observed). The actionable signal is
    'the GPU box is down', which one line conveys; the per-file repetition is
    noise. Process-scoped: a fresh compile/producer process re-warns once.
    """
    global _UNREACHABLE_WARNED
    prefix = f"{context}: " if context else ""
    msg = f"{prefix}Ollama not reachable at {_base_url()} — skipping"
    if _UNREACHABLE_WARNED:
        log.debug(msg)
    else:
        _UNREACHABLE_WARNED = True
        log.warning("%s (further offline skips this run logged at DEBUG)", msg)


# ── JSON extraction ───────────────────────────────────────────────────

def strip_fences(text: str) -> str:
    """Remove leading/trailing markdown code fences if present."""
    text = text.strip()
    if not text.startswith("```"):
        return text
    text = _FENCE_LEADING.sub("", text, count=1)
    text = _FENCE_TRAILING.sub("", text)
    return text.strip()


def parse_json_lenient(text: str) -> Any:
    """json.loads after stripping fences. Falls back to outermost {...} block.

    Raises json.JSONDecodeError if no valid JSON can be extracted.
    """
    cleaned = strip_fences(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(cleaned[start:end])
        raise


# ── Chat variants ─────────────────────────────────────────────────────

def chat(
    prompt: str,
    *,
    model: str,
    temperature: float = 0.1,
    timeout: float = 120.0,
) -> str:
    """Plain text chat via the OpenAI-compatible endpoint.

    Returns the assistant message content (stripped). Pair with
    `parse_json_lenient` when the prompt asks for JSON.
    """
    with _client(timeout) as c:
        r = c.post(
            f"{_base_url()}/v1/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
            },
        )
    r.raise_for_status()
    data = r.json()
    LEDGER.record_openai_usage(model, data.get("usage", {}))
    return data["choices"][0]["message"]["content"].strip()


def chat_schema(
    prompt: str,
    *,
    model: str,
    schema: dict,
    temperature: float = 0.0,
    timeout: float = 90.0,
) -> str:
    """Constrained-decoding chat via the native /api/chat endpoint.

    `schema` is the JSON-Schema-shaped dict Ollama expects in `format`.
    Returns the assistant message content; pair with `parse_json_lenient`.
    """
    with _client(timeout) as c:
        r = c.post(
            f"{_base_url()}/api/chat",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "format": schema,
                "stream": False,
                "options": {"temperature": temperature},
            },
        )
    r.raise_for_status()
    data = r.json()
    LEDGER.record_ollama(model, data)
    return data.get("message", {}).get("content", "").strip()


def chat_vision(
    prompt: str,
    *,
    model: str,
    image_b64: str,
    timeout: float = 60.0,
) -> tuple[str, dict]:
    """Vision chat via /api/chat. Returns (content, stats).

    `stats` carries the raw response fields callers want for logging
    (e.g. `eval_count`).
    """
    with _client(timeout) as c:
        r = c.post(
            f"{_base_url()}/api/chat",
            json={
                "model": model,
                "messages": [{
                    "role": "user",
                    "content": prompt,
                    "images": [image_b64],
                }],
                "stream": False,
            },
        )
    r.raise_for_status()
    data = r.json()
    content = data.get("message", {}).get("content", "")
    stats = {k: v for k, v in data.items() if k != "message"}
    LEDGER.record_ollama(model, stats)
    return content, stats
