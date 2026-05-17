"""Tests for the pre-flight prompt-size guard in `core.sdk_helpers`.

`assert_prompt_within_budget` is the defense-in-depth layer for the
context-overflow root cause (KNOWLEDGE.md, 2026-05-13/14 entries): it
turns an opaque exit-1 / empty-stderr `kind=unknown` SDK death into a
clear operator message *before* the SDK call.
"""

from __future__ import annotations

import pytest

from core.sdk_helpers import PromptTooLargeError, assert_prompt_within_budget


def test_under_budget_does_not_raise() -> None:
    assert_prompt_within_budget(100, 500, label="query") is None


def test_at_budget_does_not_raise() -> None:
    # Boundary: exactly at the limit is allowed.
    assert_prompt_within_budget(500, 500, label="query") is None


def test_over_budget_raises() -> None:
    with pytest.raises(PromptTooLargeError):
        assert_prompt_within_budget(501, 500, label="query")


def test_message_carries_size_limit_and_label() -> None:
    with pytest.raises(PromptTooLargeError) as exc_info:
        assert_prompt_within_budget(4_484_234, 500_000, label="query")
    msg = str(exc_info.value)
    assert "query" in msg
    assert "4,484,234" in msg
    assert "500,000" in msg


def test_message_includes_breakdown_components() -> None:
    with pytest.raises(PromptTooLargeError) as exc_info:
        assert_prompt_within_budget(
            900_000,
            500_000,
            label="query",
            breakdown={"compact index": 850_000, "hard facts": 50_000},
        )
    msg = str(exc_info.value)
    assert "compact index 850,000 chars" in msg
    assert "hard facts 50,000 chars" in msg


def test_breakdown_optional() -> None:
    # No breakdown -> message goes straight from the budget to the advice,
    # with no per-component clause spliced in.
    with pytest.raises(PromptTooLargeError) as exc_info:
        assert_prompt_within_budget(600_000, 500_000, label="optimize_claude_md")
    msg = str(exc_info.value)
    assert "optimize_claude_md" in msg
    assert "budget. The input has outgrown" in msg  # no breakdown clause spliced in


# ── Path-scope gate ────────────────────────────────────────────────────


import asyncio
from pathlib import Path

from core.sdk_helpers import make_path_scope_gate, prompt_stream


def _run(coro):
    return asyncio.run(coro)


def test_gate_allows_write_inside_scope(tmp_path):
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    gate = make_path_scope_gate([knowledge])
    target = str(knowledge / "foo.md")
    result = _run(gate("Write", {"file_path": target}, None))
    assert result.behavior == "allow"


def test_gate_denies_write_outside_scope(tmp_path):
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    gate = make_path_scope_gate([knowledge])
    target = str(tmp_path / "outside.md")
    result = _run(gate("Write", {"file_path": target}, None))
    assert result.behavior == "deny"
    assert "path-scope" in result.message
    assert str(tmp_path / "outside.md") in result.message


def test_gate_denies_edit_outside_scope(tmp_path):
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    gate = make_path_scope_gate([knowledge])
    target = str(tmp_path / "outside.md")
    result = _run(gate("Edit", {"file_path": target}, None))
    assert result.behavior == "deny"


def test_gate_allows_read_unconditionally(tmp_path):
    gate = make_path_scope_gate([tmp_path / "knowledge"])
    # Read outside the allowed roots is still permitted — gating non-write
    # tools is the caller's job via allowed_tools, not the gate's.
    result = _run(gate("Read", {"file_path": "/etc/passwd"}, None))
    assert result.behavior == "allow"


def test_gate_allows_bash_glob_grep(tmp_path):
    gate = make_path_scope_gate([tmp_path / "knowledge"])
    for tool in ("Bash", "Glob", "Grep"):
        result = _run(gate(tool, {"command": "echo hi"}, None))
        assert result.behavior == "allow", f"{tool} should pass through"


def test_gate_handles_relative_paths_via_cwd_resolution(tmp_path, monkeypatch):
    """Relative file_path resolves against the test's cwd, not the gate's
    root list — proving the gate stays honest with the filesystem-level
    resolution `pathlib.Path.resolve()` performs."""
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    gate = make_path_scope_gate([knowledge])
    # Inside-scope cwd: resolves to <knowledge>/foo.md → allow.
    monkeypatch.chdir(knowledge)
    result_in = _run(gate("Write", {"file_path": "foo.md"}, None))
    assert result_in.behavior == "allow"
    # Outside-scope cwd: resolves to <tmp_path>/foo.md → deny.
    monkeypatch.chdir(tmp_path)
    result_out = _run(gate("Write", {"file_path": "foo.md"}, None))
    assert result_out.behavior == "deny"


def test_gate_denies_write_with_missing_file_path():
    gate = make_path_scope_gate([Path("/tmp/x")])
    result = _run(gate("Write", {}, None))
    assert result.behavior == "deny"
    assert "missing file_path" in result.message


def test_gate_supports_multiple_roots(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    gate = make_path_scope_gate([a, b])
    assert _run(gate("Write", {"file_path": str(a / "x.md")}, None)).behavior == "allow"
    assert _run(gate("Write", {"file_path": str(b / "y.md")}, None)).behavior == "allow"
    assert _run(gate("Write", {"file_path": str(tmp_path / "z.md")}, None)).behavior == "deny"


def test_prompt_stream_yields_one_user_message():
    async def collect():
        out = []
        async for msg in prompt_stream("hello world"):
            out.append(msg)
        return out
    msgs = _run(collect())
    assert msgs == [{"type": "user", "message": {"role": "user", "content": "hello world"}}]
