"""Shared transcript-extraction helpers for session-end and pre-compact hooks.

Both hooks do the same thing: read a JSONL transcript, summarize it, build
a markdown context, and stage it via flush_pipeline. Only the staging kind
and the MIN_TURNS_TO_FLUSH threshold differ — those stay in the caller.
Everything else lives here.

The rich tool-block summarizer (Edit/Write/Bash/Read details) is the
correct version per .ytstack/KNOWLEDGE.md ("summarize tool inputs,
truncate tool results"). The lossy `[tool: X]` / `[tool result]` shape
pre-compact used to ship was the Karpathy/Cole anti-pattern; the compiler
needs file paths and command lines to be useful.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

MAX_TURNS = 30
MAX_CONTEXT_CHARS = 15_000
TOOL_RESULT_TRUNC = 300  # chars per tool_result
TOOL_INPUT_TRUNC = 150   # chars per input field


def _truncate(s: str, n: int) -> str:
    s = s.replace("\n", " ").strip()
    return s if len(s) <= n else s[:n] + "…"


def _summarize_tool(name: str, inp: dict) -> str:
    """Produce a one-line summary for a tool_use block."""
    if not isinstance(inp, dict):
        return f"[{name}]"

    if name == "Edit":
        fp = inp.get("file_path", "?")
        old = _truncate(inp.get("old_string", ""), TOOL_INPUT_TRUNC)
        new = _truncate(inp.get("new_string", ""), TOOL_INPUT_TRUNC)
        return f"[Edit] {fp}\n  - {old}\n  + {new}"
    if name == "Write":
        fp = inp.get("file_path", "?")
        content = inp.get("content", "")
        return f"[Write] {fp} ({len(content)} chars): {_truncate(content, TOOL_INPUT_TRUNC)}"
    if name == "Read":
        fp = inp.get("file_path", "?")
        return f"[Read] {fp}"
    if name == "Bash":
        cmd = _truncate(inp.get("command", ""), TOOL_INPUT_TRUNC)
        return f"[Bash] {cmd}"
    if name == "Grep":
        pat = inp.get("pattern", "")
        path = inp.get("path", ".")
        return f"[Grep] {pat!r} in {path}"
    if name == "Glob":
        pat = inp.get("pattern", "")
        return f"[Glob] {pat}"
    if name == "WebFetch":
        return f"[WebFetch] {inp.get('url', '?')}"
    if name == "WebSearch":
        return f"[WebSearch] {_truncate(inp.get('query', ''), 100)}"
    if name == "TodoWrite":
        todos = inp.get("todos", [])
        return f"[TodoWrite] {len(todos)} item(s)"
    if name == "Task" or name == "Agent":
        desc = _truncate(inp.get("description", ""), 80)
        return f"[Agent] {desc}"
    if name == "Skill":
        return f"[Skill] {inp.get('skill', '?')}"
    # Fallback: include first meaningful field
    for key in ("file_path", "path", "query", "url", "command", "name"):
        if key in inp:
            return f"[{name}] {key}={_truncate(str(inp[key]), 100)}"
    return f"[{name}]"


def _summarize_tool_result(block: dict) -> str:
    """Produce a truncated tool_result summary."""
    content = block.get("content", "")
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text":
                parts.append(b.get("text", ""))
            elif isinstance(b, str):
                parts.append(b)
        content = "\n".join(parts)
    if not isinstance(content, str):
        content = str(content)
    if block.get("is_error"):
        return f"→ ERROR: {_truncate(content, TOOL_RESULT_TRUNC)}"
    return f"→ {_truncate(content, TOOL_RESULT_TRUNC)}"


def extract_text(content) -> str:
    """Extract text from a message content field, keeping tool signal."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                btype = block.get("type")
                if btype == "text":
                    parts.append(block.get("text", ""))
                elif btype == "tool_use":
                    parts.append(_summarize_tool(block.get("name", "?"), block.get("input", {})))
                elif btype == "tool_result":
                    parts.append(_summarize_tool_result(block))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(p for p in parts if p)
    return str(content)


def read_transcript(transcript_path: str) -> list[dict]:
    """Read JSONL transcript and extract conversation turns."""
    turns: list[dict] = []
    path = Path(transcript_path)
    if not path.exists():
        log.warning(f"Transcript not found: {transcript_path}")
        return turns

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg = entry.get("message", {})
            role = msg.get("role")
            content = msg.get("content")

            if role in ("user", "assistant") and content:
                text = extract_text(content)
                if text.strip():
                    turns.append({"role": role, "text": text})

    return turns


def build_context(turns: list[dict]) -> str:
    """Build markdown context from conversation turns. Caps at MAX_CONTEXT_CHARS."""
    recent = turns[-MAX_TURNS:]

    parts: list[str] = []
    for turn in recent:
        prefix = "## User" if turn["role"] == "user" else "## Assistant"
        parts.append(f"{prefix}\n\n{turn['text']}")

    context = "\n\n---\n\n".join(parts)

    if len(context) > MAX_CONTEXT_CHARS:
        context = context[:MAX_CONTEXT_CHARS] + "\n\n[... truncated ...]"

    return context
