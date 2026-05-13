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
import re
from typing import Any

import httpx

from .wiki_config import CONFIG


_FENCE_LEADING = re.compile(r"^```[a-zA-Z]*\s*", flags=re.MULTILINE)
_FENCE_TRAILING = re.compile(r"\s*```\s*$", flags=re.MULTILINE)


def _base_url() -> str:
    return CONFIG.models.ollama_url.rstrip("/")


# ── Liveness ──────────────────────────────────────────────────────────

def is_reachable(timeout: float = 5.0) -> bool:
    """Quick GET /api/tags. Used before kicking off long batches."""
    try:
        r = httpx.get(f"{_base_url()}/api/tags", timeout=timeout)
        return r.status_code == 200
    except Exception:
        return False


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
    r = httpx.post(
        f"{_base_url()}/v1/chat/completions",
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
        },
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


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
    r = httpx.post(
        f"{_base_url()}/api/chat",
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "format": schema,
            "stream": False,
            "options": {"temperature": temperature},
        },
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json().get("message", {}).get("content", "").strip()


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
    r = httpx.post(
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
        timeout=timeout,
    )
    r.raise_for_status()
    data = r.json()
    content = data.get("message", {}).get("content", "")
    stats = {k: v for k, v in data.items() if k != "message"}
    return content, stats
