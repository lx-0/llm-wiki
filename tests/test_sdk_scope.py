"""Tests for the Write/Edit path-scope gate in `core.sdk_scope`.

`make_path_scope_hook` is the production gate — the PreToolUse hook the
`run_sdk_query` harness wires for every write-scoped call; `make_path_scope_gate`
is the `can_use_tool` form behind the deny-all-writes wedge; `prompt_stream` wraps
a string prompt in the streaming envelope the callback contract requires.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from core.sdk_scope import make_path_scope_gate, make_path_scope_hook, prompt_stream


def _run(coro):
    return asyncio.run(coro)


# ── make_path_scope_hook — the production compile/dream gate (PreToolUse) ──
# This is the path actually wired when `features.compile_callback_gate` is True
# (compile.py + dream.py). It returns the PreToolUse hookSpecificOutput shape,
# NOT the can_use_tool PermissionResult shape — different contract, so it needs
# its own coverage. (The can_use_tool gate above silently blocked inside-scope
# writes in production, which is why the hook superseded it — 2026-05-18.)


def _hook_decision(hook, *, tool, file_path):
    out = _run(hook({"tool_name": tool, "tool_input": {"file_path": file_path}}, "tid", None))
    return out["hookSpecificOutput"]


def test_hook_allows_write_inside_scope(tmp_path):
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    hook = make_path_scope_hook([knowledge])
    d = _hook_decision(hook, tool="Write", file_path=str(knowledge / "foo.md"))
    assert d["permissionDecision"] == "allow"
    assert d["hookEventName"] == "PreToolUse"


def test_hook_denies_write_outside_scope(tmp_path):
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    hook = make_path_scope_hook([knowledge])
    target = str(tmp_path / ".wiki" / "config.yaml")  # engine-targeted write
    d = _hook_decision(hook, tool="Write", file_path=target)
    assert d["permissionDecision"] == "deny"
    assert "not under any permitted root" in d["permissionDecisionReason"]


def test_hook_denies_edit_outside_scope(tmp_path):
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    hook = make_path_scope_hook([knowledge])
    d = _hook_decision(hook, tool="Edit", file_path=str(tmp_path / "outside.md"))
    assert d["permissionDecision"] == "deny"


def test_hook_denies_missing_file_path(tmp_path):
    hook = make_path_scope_hook([tmp_path / "knowledge"])
    out = _run(hook({"tool_name": "Write", "tool_input": {}}, "tid", None))
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_hook_multi_root_allows_log_file(tmp_path):
    """Production scopes to [knowledge/, LOG_FILE] — both roots must allow."""
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    log_file = tmp_path / ".wiki" / "logs" / "operations.md"
    hook = make_path_scope_hook([knowledge, log_file])
    # The operations log (a second permitted root) is writable…
    assert (
        _hook_decision(hook, tool="Write", file_path=str(log_file))["permissionDecision"] == "allow"
    )
    # …but a sibling engine file is not.
    sibling = str(tmp_path / ".wiki" / "config.yaml")
    assert _hook_decision(hook, tool="Write", file_path=sibling)["permissionDecision"] == "deny"


def test_hook_denied_subpath_overrides_allowed_root(tmp_path):
    """M028-S01-T02: `correct apply` writes across knowledge/ EXCEPT facts/.

    `denied_subpaths` carves a write-protected island out of an allowed root.
    Deny takes precedence over allow.
    """
    knowledge = tmp_path / "knowledge"
    facts = knowledge / "facts"
    facts.mkdir(parents=True)
    hook = make_path_scope_hook([knowledge], denied_subpaths=[facts])
    # knowledge/concepts/ — allowed.
    assert (
        _hook_decision(hook, tool="Write", file_path=str(knowledge / "concepts" / "x.md"))[
            "permissionDecision"
        ]
        == "allow"
    )
    # knowledge/facts/ — denied even though it is inside the allowed root.
    d = _hook_decision(hook, tool="Write", file_path=str(facts / "x.md"))
    assert d["permissionDecision"] == "deny"
    assert "facts" in d["permissionDecisionReason"]


def test_hook_denied_subpaths_defaults_to_none(tmp_path):
    """No denied_subpaths → unchanged behaviour (backward compat)."""
    knowledge = tmp_path / "knowledge"
    (knowledge / "facts").mkdir(parents=True)
    hook = make_path_scope_hook([knowledge])  # no denied_subpaths kwarg
    assert (
        _hook_decision(hook, tool="Write", file_path=str(knowledge / "facts" / "x.md"))[
            "permissionDecision"
        ]
        == "allow"
    )


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


# ── no call site auto-accepts edits without a scope (AGENTS.md HARD rule) ──
# `wiki query` ran `permission_mode="acceptEdits"` with the default toolset and no scope
# until M034-S06-T07: every mode could write anywhere in the vault. A literal acceptEdits
# with no `write_scope` in the same SdkCallSpec is that shape. (Agent tasks pass their spec's
# mode through a variable — backlog `agent-task-write-scope.md`.)


def _unscoped_accept_edits(source: str) -> list[int]:
    import ast

    lines = []
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "SdkCallSpec"):
            continue
        kwargs = {kw.arg: kw.value for kw in node.keywords}
        mode = kwargs.get("permission_mode")
        if (
            isinstance(mode, ast.Constant)
            and mode.value == "acceptEdits"
            and "write_scope" not in kwargs
        ):
            lines.append(node.lineno)
    return lines


def test_the_guard_sees_the_old_query_shape():
    old = 'SdkCallSpec(label="query", allowed_tools=("Read",), permission_mode="acceptEdits")'
    assert _unscoped_accept_edits(old) == [1]
    scoped = 'SdkCallSpec(permission_mode="acceptEdits", write_scope=WriteScope(roots=()))'
    assert _unscoped_accept_edits(scoped) == []


def test_no_sdk_call_site_auto_accepts_edits_without_a_scope():
    scripts = Path(__file__).resolve().parent.parent / "scripts"
    found = [
        f"{path.relative_to(scripts)}:{line}"
        for path in sorted(scripts.rglob("*.py"))
        for line in _unscoped_accept_edits(path.read_text(encoding="utf-8"))
    ]
    assert found == []
