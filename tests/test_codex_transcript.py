"""Codex-rollout transcript ingestion (hooks/_transcript.py) + multi-fire
coalescing (core/flush_pipeline.append_to_daily).

Regression guard for the silent-capture bug: `read_transcript` used to parse
ONLY the Claude Code JSONL schema (`message.role`/`message.content`), so every
Codex rollout (`{timestamp, type, payload}`, no top-level `message`) yielded 0
turns and was skipped. Fixture is built from REAL Codex rollout lines
(tests/fixtures/codex_rollout_sample.jsonl) — see backlog/codex-session-capture.md.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_HOOKS = Path(__file__).resolve().parent.parent / "hooks"
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

import _transcript  # noqa: E402
from _transcript import read_transcript  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "codex_rollout_sample.jsonl"


# ── Format detection ─────────────────────────────────────────────────

def test_detect_codex_format():
    assert _transcript._detect_format(FIXTURE) == "codex"


def test_detect_claude_format(tmp_path: Path):
    p = tmp_path / "claude.jsonl"
    p.write_text(
        json.dumps({"message": {"role": "user", "content": "hi"}}) + "\n"
        + json.dumps({"message": {"role": "assistant", "content": [{"type": "text", "text": "yo"}]}}) + "\n",
        encoding="utf-8",
    )
    assert _transcript._detect_format(p) == "claude"


# ── Codex parser ─────────────────────────────────────────────────────

def test_codex_parser_returns_turns():
    turns = _transcript._read_codex_transcript(FIXTURE)
    assert len(turns) > 0, "Codex rollout must yield turns (this was the bug: 0)"


def test_codex_user_prose_comes_from_clean_event_msg_not_agents_wrapper():
    turns = _transcript._read_codex_transcript(FIXTURE)
    joined = "\n".join(t.text for t in turns if t.role == "user")
    assert "Add a helper that reverses a string" in joined
    # The response_item/message role=user variant is polluted with the injected
    # AGENTS.md / environment context — it must NOT leak into captured prose.
    assert "AGENTS.md instructions" not in joined


def test_codex_assistant_prose_from_output_text():
    turns = _transcript._read_codex_transcript(FIXTURE)
    joined = "\n".join(t.text for t in turns if t.role == "assistant")
    assert "I'll add a reverse_string helper" in joined


def test_codex_tool_calls_captured():
    turns = _transcript._read_codex_transcript(FIXTURE)
    tools = "\n".join(tool for t in turns for tool in t.tools)
    assert "search" in tools          # function_call (mcp semble)
    assert "apply_patch" in tools     # custom_tool_call


def test_codex_skips_reasoning_and_developer_noise():
    turns = _transcript._read_codex_transcript(FIXTURE)
    blob = "\n".join(t.text for t in turns) + "\n".join(x for t in turns for x in t.tools)
    # Encrypted reasoning payload must never surface.
    assert "gAAAAA" not in blob
    # developer/permissions instructions are noise, not conversation.
    assert "Filesystem sandboxing" not in blob


# ── Dispatcher: the real integration that was broken ─────────────────

def test_read_transcript_dispatches_codex_rollout():
    turns = read_transcript(str(FIXTURE))
    assert len(turns) > 0, "read_transcript must now handle Codex rollouts"
    roles = {t.role for t in turns}
    assert "user" in roles and "assistant" in roles


def test_read_transcript_claude_regression(tmp_path: Path):
    p = tmp_path / "claude.jsonl"
    p.write_text(
        json.dumps({"message": {"role": "user", "content": "hello"}}) + "\n"
        + json.dumps({"message": {"role": "assistant", "content": [
            {"type": "text", "text": "world"},
            {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}},
        ]}}) + "\n",
        encoding="utf-8",
    )
    turns = read_transcript(str(p))
    assert any("hello" in t.text for t in turns)
    assert any("world" in t.text for t in turns)
    assert any("[Bash] ls" in x for t in turns for x in t.tools)


# ── Resolution fallback (fixes the 287 "Transcript not found") ────────

def test_resolve_transcript_prefers_existing_path():
    got = _transcript.resolve_transcript(str(FIXTURE), session_id=None)
    assert got == FIXTURE


def test_resolve_transcript_falls_back_to_codex_rollout_glob(tmp_path, monkeypatch):
    sid = "019f5ac6-643a-7371-bbe8-54114c79c0fd"
    day = tmp_path / "sessions" / "2026" / "07" / "13"
    day.mkdir(parents=True)
    rollout = day / f"rollout-2026-07-13T11-19-39-{sid}.jsonl"
    rollout.write_text("{}\n", encoding="utf-8")
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    # transcript_path is missing/unresolvable → resolve by session_id
    got = _transcript.resolve_transcript("/nonexistent/path.jsonl", session_id=sid)
    assert got == rollout


def test_resolve_transcript_returns_none_when_unresolvable(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    got = _transcript.resolve_transcript("", session_id="unknown")
    assert got is None
