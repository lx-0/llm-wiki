"""Shared transcript-extraction helpers for session-end and pre-compact hooks.

Both hooks do the same thing: read a JSONL transcript, split each message into
its user-text / assistant-text / tool-summary streams, apply per-class budgets,
build a markdown context, and stage it via flush_pipeline. Only the staging
kind and the MIN_TURNS_TO_FLUSH threshold differ — those stay in the caller.

## Why per-class budgets (gen-2, 2026-05-16)

The pre-2026-05-16 design (MAX_TURNS=30 + MAX_CONTEXT_CHARS=15_000 global) was
content-blind. A tool-heavy session pushed the whole 15 KB into truncated tool
dumps and lost the assistant prose where the actual analytical findings live
(2026-05-16 ROM-session incident: long preference-analysis session, only
memories survived; the analysis itself never reached compile.py because it
was beyond turn 30 + truncated past 15 K total chars).

The fix: separate budgets per content class. Assistant prose gets a generous
50 KB so a full long-analysis session survives intact; user text gets 10 KB
(prompts are short); tool summaries get 10 KB on top of the existing per-line
300/150-char caps. Allocation is prefer-tail (newest first); if a session
exceeds budget the opening warm-up drops, not the recent state.

This is the asymmetric-truncation variant from the OpenCode / Anthropic
compaction-doc family. Recursive summary for >60-turn sessions is the
Phase-2 backlog (.ytstack/backlog/recursive-session-summary.md).

## Why summarize tool blocks at all

The original `[tool: X]` / `[tool result]` mapping (Cole Medin's
claude-memory-compiler) drops 90 % of agentic-session signal: the compiler no
longer knows what files were touched or which commands ran. Our rich one-line
summaries (Edit/Write/Bash/Read details, truncated tool results) keep the
provenance the compiler needs. See KNOWLEDGE.md "Flush context — Karpathy/Cole
pattern" sections (gen-1 and gen-2).
"""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

# Per-result/-input chars (apply BEFORE class budgets — low-signal noise).
TOOL_RESULT_TRUNC = 300
TOOL_INPUT_TRUNC = 150

# Fallback budgets when the engine CONFIG isn't importable (dev, standalone
# tests). Real installs override via CONFIG.limits.flush_*_budget_chars below.
DEFAULT_ASSISTANT_TEXT_BUDGET = 50_000
DEFAULT_USER_TEXT_BUDGET = 10_000
DEFAULT_TOOL_SUMMARY_BUDGET = 10_000


@dataclass
class Budgets:
    """Per-class char budgets applied to the flush context."""

    assistant_text: int = DEFAULT_ASSISTANT_TEXT_BUDGET
    user_text: int = DEFAULT_USER_TEXT_BUDGET
    tool_summary: int = DEFAULT_TOOL_SUMMARY_BUDGET

    @classmethod
    def from_config(cls) -> Budgets:
        """Load budgets from engine CONFIG; fall back to defaults if unavailable."""
        try:
            _scripts = Path(__file__).resolve().parent.parent / "scripts"
            if str(_scripts) not in sys.path:
                sys.path.insert(0, str(_scripts))
            from core.config import CONFIG  # type: ignore[import-not-found]

            return cls(
                assistant_text=CONFIG.limits.flush_assistant_text_budget_chars,
                user_text=CONFIG.limits.flush_user_text_budget_chars,
                tool_summary=CONFIG.limits.flush_tool_summary_budget_chars,
            )
        except Exception:  # noqa: BLE001  config-load failure must never break flush
            return cls()


@dataclass
class Turn:
    """One transcript turn split into per-class streams."""

    role: str            # "user" | "assistant"
    text: str = ""       # prose (everything that isn't tool_use / tool_result)
    tools: list[str] = field(default_factory=list)  # one-line tool summaries


def _truncate(s: str, n: int) -> str:
    s = s.replace("\n", " ").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def _summarize_tool(name: str, inp: dict) -> str:
    """One-line summary for a tool_use block. Truncation: low-signal fields only."""
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
    for key in ("file_path", "path", "query", "url", "command", "name"):
        if key in inp:
            return f"[{name}] {key}={_truncate(str(inp[key]), 100)}"
    return f"[{name}]"


def _summarize_tool_result(block: dict) -> str:
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


def _split_content(content) -> tuple[str, list[str]]:
    """Return (prose-text, [tool-summaries]) for a message content payload.

    Tool_use and tool_result blocks become one-line summaries (their lifecycle
    is "compress, don't drop" — see Karpathy/Cole notes in KNOWLEDGE.md).
    Everything else concatenates into the prose stream.
    """
    if isinstance(content, str):
        return content, []
    if not isinstance(content, list):
        return str(content), []

    text_parts: list[str] = []
    tool_parts: list[str] = []
    for block in content:
        if isinstance(block, dict):
            btype = block.get("type")
            if btype == "text":
                text_parts.append(block.get("text", ""))
            elif btype == "tool_use":
                tool_parts.append(_summarize_tool(block.get("name", "?"), block.get("input", {})))
            elif btype == "tool_result":
                tool_parts.append(_summarize_tool_result(block))
        elif isinstance(block, str):
            text_parts.append(block)
    return "\n".join(t for t in text_parts if t), tool_parts


def read_transcript(transcript_path: str, session_id: str | None = None) -> list[Turn]:
    """Read a session transcript (Claude Code OR Codex rollout) into Turns.

    Format-aware dispatcher. The agent hooks (session-end, pre-compact) are
    installed for every agent (`.claude`, `.codex`, `.gemini`, `.cursor`) but
    each agent writes a different transcript schema. This resolves the actual
    transcript file (falling back to the session-id → Codex-rollout glob when
    the hook-supplied `transcript_path` is missing), sniffs its format, and
    parses with the matching reader.

    History: before 2026-07-14 this parsed ONLY the Claude schema, so every
    Codex session yielded 0 turns and was silently skipped. See
    `.ytstack/backlog/codex-session-capture.md`.
    """
    resolved = resolve_transcript(transcript_path, session_id)
    if resolved is None:
        log.warning(
            "Transcript not found (path=%r session=%r)", transcript_path, session_id
        )
        return []
    if _detect_format(resolved) == "codex":
        return _read_codex_transcript(resolved)
    return _read_claude_transcript(resolved)


# ── Transcript resolution + format detection ─────────────────────────

# Top-level `type` values that mark a Codex rollout line (`{timestamp, type,
# payload}`). Distinct from the Claude schema, whose lines carry a `message`
# object with a `role`.
_CODEX_TOP_TYPES = frozenset({
    "session_meta", "response_item", "event_msg", "turn_context",
    "world_state", "compacted", "inter_agent_communication_metadata",
})


def resolve_transcript(transcript_path: str | None, session_id: str | None) -> Path | None:
    """Return the transcript file to read, or None if unresolvable.

    Prefers the hook-supplied path when it exists. Falls back to locating a
    Codex rollout by session id under `$CODEX_HOME` (default `~/.codex`) —
    Codex's `Stop` hook sometimes passes a path the engine can't resolve
    (287 `Transcript not found` in flush.log); the rollout id equals the
    session id, so the glob recovers it.
    """
    if transcript_path:
        p = Path(transcript_path)
        if p.exists():
            return p
    if session_id and session_id not in ("", "unknown"):
        codex_home = Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex"))
        matches = sorted(codex_home.glob(f"sessions/**/rollout-*-{session_id}.jsonl"))
        if matches:
            return matches[-1]  # names are timestamp-prefixed → newest last
    return None


def _detect_format(path: Path) -> str:
    """Sniff "claude" vs "codex" from the first parseable lines. Defaults claude."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            checked = 0
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(entry.get("payload"), dict) and entry.get("type") in _CODEX_TOP_TYPES:
                    return "codex"
                msg = entry.get("message")
                if isinstance(msg, dict) and msg.get("role") in ("user", "assistant"):
                    return "claude"
                checked += 1
                if checked >= 15:
                    break
    except OSError:
        pass
    return "claude"


def _read_claude_transcript(transcript_path: str | Path) -> list[Turn]:
    """Read a Claude Code JSONL transcript and return ordered Turns.

    A Turn is dropped only if it produces no prose AND no tool summaries —
    pure system/metadata entries. Empty assistant prose with tool calls is
    kept (it carries the tool-sequence the compiler depends on).
    """
    turns: list[Turn] = []
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

            if role not in ("user", "assistant") or content is None:
                continue

            text, tools = _split_content(content)
            text = text.strip()
            if not text and not tools:
                continue
            turns.append(Turn(role=role, text=text, tools=tools))

    return turns


# ── Codex rollout reader ─────────────────────────────────────────────
# Codex records a Responses-API rollout: one JSONL line per {timestamp, type,
# payload}. Canonical, de-duplicated streams (see backlog/codex-session-capture.md):
#   user prose      ← event_msg / user_message.message   (clean; the
#                     response_item/message role=user variant is polluted with
#                     the injected AGENTS.md / environment context)
#   assistant prose ← response_item / message role=assistant → output_text
#   tools           ← response_item / {function_call, custom_tool_call,
#                     web_search_call, tool_search_call} + their *_output
#   skipped         ← developer/system messages, reasoning (encrypted), and
#                     every other type (streaming duplicates + metadata)

_CODEX_TOOL_CALL_TYPES = frozenset({
    "function_call", "custom_tool_call", "web_search_call", "tool_search_call",
})
_CODEX_TOOL_OUTPUT_TYPES = frozenset({
    "function_call_output", "custom_tool_call_output", "tool_search_output",
})


def _codex_message_text(payload: dict) -> str:
    """Join the text content items of a Codex response_item/message payload."""
    parts: list[str] = []
    for c in payload.get("content") or []:
        if isinstance(c, dict) and c.get("type") in ("output_text", "input_text", "text"):
            t = c.get("text")
            if t:
                parts.append(t)
    return "\n".join(parts)


def _summarize_codex_tool(payload: dict) -> str | None:
    """One-line summary for a Codex tool call / output payload."""
    pt = payload.get("type")
    if pt == "function_call":
        name = payload.get("name", "?")
        ns = payload.get("namespace")
        label = f"{ns}/{name}" if ns else name
        return f"[{label}] {_truncate(str(payload.get('arguments', '')), TOOL_INPUT_TRUNC)}"
    if pt == "custom_tool_call":
        return f"[{payload.get('name', '?')}] {_truncate(str(payload.get('input', '')), TOOL_INPUT_TRUNC)}"
    if pt in ("function_call_output", "custom_tool_call_output"):
        out = payload.get("output", "")
        if isinstance(out, dict):
            out = out.get("content") or json.dumps(out, default=str)
        return f"→ {_truncate(str(out), TOOL_RESULT_TRUNC)}"
    if pt == "web_search_call":
        action = payload.get("action") or {}
        return f"[web_search] {_truncate(str(action.get('query', '')), 100)}"
    if pt == "tool_search_call":
        return "[tool_search]"
    if pt == "tool_search_output":
        return "→ (tool_search results)"
    return None


def _read_codex_transcript(transcript_path: str | Path) -> list[Turn]:
    """Read a Codex rollout JSONL and return ordered Turns."""
    turns: list[Turn] = []
    path = Path(transcript_path)
    if not path.exists():
        log.warning(f"Transcript not found: {transcript_path}")
        return turns

    def push_tool(summary: str | None) -> None:
        if not summary:
            return
        # Codex logs tool calls as their own top-level items, separate from the
        # assistant message. Attach to the nearest assistant turn so they get
        # the tool-summary budget; open a tools-only assistant turn if needed.
        if turns and turns[-1].role == "assistant":
            turns[-1].tools.append(summary)
        else:
            turns.append(Turn(role="assistant", text="", tools=[summary]))

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            t = entry.get("type")
            payload = entry.get("payload")
            if not isinstance(payload, dict):
                continue
            pt = payload.get("type")

            if t == "event_msg" and pt == "user_message":
                msg = payload.get("message")
                if isinstance(msg, str) and msg.strip():
                    turns.append(Turn(role="user", text=msg.strip(), tools=[]))
            elif t == "response_item" and pt == "message":
                if payload.get("role") == "assistant":
                    text = _codex_message_text(payload).strip()
                    if text:
                        turns.append(Turn(role="assistant", text=text, tools=[]))
                # role user/developer/system skipped: user prose comes from the
                # clean event_msg/user_message; developer/system = instructions.
            elif t == "response_item" and pt in _CODEX_TOOL_CALL_TYPES:
                push_tool(_summarize_codex_tool(payload))
            elif t == "response_item" and pt in _CODEX_TOOL_OUTPUT_TYPES:
                push_tool(_summarize_codex_tool(payload))
            # everything else (reasoning, session_meta, token_count, turn_context,
            # world_state, compacted, sub_agent_activity, …) is metadata/noise.

    return turns


def _truncate_tail(s: str, budget: int) -> str:
    """Truncate s to fit budget chars, preserving the tail (most recent text).

    Adds a leading "[... truncated …]" marker so the consumer knows prose was
    cut. Returns "" when budget <= 0.
    """
    if budget <= 0:
        return ""
    if len(s) <= budget:
        return s
    marker = "[... truncated ...]\n"
    keep = budget - len(marker)
    if keep <= 0:
        return marker[:budget]
    return marker + s[-keep:]


def build_context(turns: list[Turn] | list[dict], *, budgets: Budgets | None = None) -> str:
    """Render Turns into the markdown context the flush extractor consumes.

    Per-class budgets (prefer-tail allocation):
      - assistant text: high-signal prose stays whole up to its budget
      - user text:      separate budget (typically short)
      - tool summaries: capped on top of per-line 300/150-char truncation

    A turn is included if any of its content (text or tools) survives the
    budget walk. Turns are emitted chronologically. When a class budget would
    overflow inside a single turn, that turn's contribution to that class is
    tail-truncated; the other classes are unaffected.

    Accepts either list[Turn] (new shape) or list[dict] with {role, text}
    (legacy shape pre-gen-2) — the legacy form is treated as pure prose with
    no tool stream.
    """
    if budgets is None:
        budgets = Budgets.from_config()

    # Legacy shim: callers that still pass [{role, text}] get the prose-only
    # path. No new caller should pass this — it's just here so a partial
    # update doesn't crash.
    normalised: list[Turn] = []
    for t in turns:
        if isinstance(t, Turn):
            normalised.append(t)
        elif isinstance(t, dict):
            normalised.append(Turn(role=t.get("role", "user"), text=str(t.get("text", "")), tools=[]))
    turns = normalised

    # Pass 1: walk newest → oldest, pull each turn's contribution into the
    # right budget. We track per-turn "kept text" and "kept tools" so Pass 2
    # can emit the chronological version without re-truncating.
    remaining = {
        "assistant_text": budgets.assistant_text,
        "user_text": budgets.user_text,
        "tool_summary": budgets.tool_summary,
    }
    kept: list[tuple[Turn, str, list[str]]] = []  # in REVERSE order during pass 1

    for turn in reversed(turns):
        text_class = "assistant_text" if turn.role == "assistant" else "user_text"
        text_room = remaining[text_class]
        kept_text = ""
        if turn.text and text_room > 0:
            if len(turn.text) <= text_room:
                kept_text = turn.text
                remaining[text_class] -= len(kept_text)
            else:
                kept_text = _truncate_tail(turn.text, text_room)
                remaining[text_class] = 0

        kept_tools: list[str] = []
        tool_room = remaining["tool_summary"]
        # Tool order matters — walk newest-first across the turn's own tools
        # too, so an over-budget turn keeps the latest tools, not the first.
        for summary in reversed(turn.tools):
            if tool_room <= 0:
                break
            cost = len(summary) + 1  # +1 for join newline
            if cost <= tool_room:
                kept_tools.append(summary)
                tool_room -= cost
        kept_tools.reverse()
        remaining["tool_summary"] = tool_room

        if kept_text or kept_tools:
            kept.append((turn, kept_text, kept_tools))

        if all(v <= 0 for v in remaining.values()):
            break  # budgets exhausted, older turns won't fit anywhere

    kept.reverse()  # back to chronological

    # Pass 2: emit.
    parts: list[str] = []
    for turn, text, tools in kept:
        prefix = "## User" if turn.role == "user" else "## Assistant"
        body_parts: list[str] = []
        if text:
            body_parts.append(text)
        if tools:
            body_parts.append("\n".join(tools))
        if body_parts:
            parts.append(f"{prefix}\n\n" + "\n\n".join(body_parts))

    return "\n\n---\n\n".join(parts)
