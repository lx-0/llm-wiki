"""Every engine SDK call must be isolated from the HOST's MCP servers.

This is the M031-S01 outage guard. From 2026-08-14 to 2026-08-25, ~99% of
session flushes died: the bundled CLI merged the host's MCP-server tool
definitions into every request, one of them ships a schema with a top-level
`oneOf`/`allOf`/`anyOf`, the API rejected it with a 400, and the CLI exited 1
with EMPTY stderr — so the only visible symptom was a retry queue growing to
234 contexts. Three other hypotheses (input size class, stale session env,
ANSI escapes) were investigated and refuted before the real cause was found.

The fix is two flags, and it had NO test: `--strict-mcp-config` plus an empty
`mcp_servers`, on BOTH paths — `core.sdk_helpers.run_sdk_query` (the harness
every producer uses) and `scripts/flush.py`, which constructs
`ClaudeAgentOptions` directly and therefore bypasses the harness entirely.
A refactor that drops either one silently reopens the outage, which is why
these assert on the options actually handed to the SDK.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


# ── the harness path ────────────────────────────────────────────────


@pytest.fixture
def captured_options(monkeypatch):
    """Run `run_sdk_query` far enough to build its ClaudeAgentOptions, then
    stop — we assert on what it would have handed the SDK. The symbol is
    imported inside the function, so the patch goes on the SDK module."""
    import claude_agent_sdk

    import core.sdk_helpers as sh

    seen: dict = {}

    class _Sentinel(Exception):
        pass

    class _FakeOptions:
        def __init__(self, **kwargs):
            seen.update(kwargs)
            raise _Sentinel

    monkeypatch.setattr(claude_agent_sdk, "ClaudeAgentOptions", _FakeOptions)
    return sh, seen, _Sentinel


def _run(sh, sentinel, **spec_kwargs):
    import asyncio
    import logging

    from core.sdk_helpers import SdkCallSpec

    spec = SdkCallSpec(label="probe", logger=logging.getLogger("probe"), **spec_kwargs)
    with pytest.raises(sentinel):
        asyncio.run(sh.run_sdk_query("hi", spec))


def test_harness_never_loads_host_mcp_servers(captured_options):
    sh, seen, sentinel = captured_options
    _run(sh, sentinel)
    assert seen.get("mcp_servers") == {}, (
        "engine SDK calls must not inherit the host's MCP servers — "
        "one of them killed every flush for eleven days"
    )
    assert "strict-mcp-config" in (seen.get("extra_args") or {}), (
        "without --strict-mcp-config the CLI merges host MCP config anyway"
    )


@pytest.mark.parametrize("spec_kwargs", [
    {},
    {"allowed_tools": ("Read",), "permission_mode": "default"},
    {"deny_all_writes": True},
    {"model": "claude-haiku-4-5-20251001", "max_turns": 3},
], ids=["plain", "tools+mode", "deny-writes", "model+turns"])
def test_harness_isolation_holds_for_every_spec_shape(captured_options, spec_kwargs):
    """The isolation is applied after the branchy per-spec options assembly.
    A refactor that moves a branch below it, or rebuilds options_kwargs, must
    not silently drop either flag on any path."""
    sh, seen, sentinel = captured_options
    _run(sh, sentinel, **spec_kwargs)
    assert seen.get("mcp_servers") == {}
    assert "strict-mcp-config" in (seen.get("extra_args") or {})


# ── the bypass path ─────────────────────────────────────────────────


def _flush_extract_options_kwargs() -> dict[str, ast.expr]:
    """Static read of the ClaudeAgentOptions(...) call inside
    flush.extract_from_context. Static because importing flush.py pulls the
    whole engine, and because the point is to catch a REFACTOR that removes
    the kwargs — which a static read catches even if the call never runs."""
    tree = ast.parse((SCRIPTS / "flush.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "extract_from_context":
            for call in ast.walk(node):
                if isinstance(call, ast.Call) and getattr(call.func, "id", "") == "ClaudeAgentOptions":
                    return {kw.arg: kw.value for kw in call.keywords if kw.arg}
    raise AssertionError("ClaudeAgentOptions(...) not found in extract_from_context")


def test_flush_bypass_path_also_isolates_mcp():
    kwargs = _flush_extract_options_kwargs()

    servers = kwargs.get("mcp_servers")
    assert servers is not None, "flush.py bypasses the harness — it must set mcp_servers itself"
    assert isinstance(servers, ast.Dict) and not servers.keys, "mcp_servers must be empty"

    extra = kwargs.get("extra_args")
    assert extra is not None and isinstance(extra, ast.Dict)
    flags = [k.value for k in extra.keys if isinstance(k, ast.Constant)]
    assert "strict-mcp-config" in flags, (
        "flush.py must pass --strict-mcp-config; it does not go through run_sdk_query"
    )


def test_flush_still_requests_zero_tools():
    """Adjacent invariant from the same call site: `tools=[]` emits an empty
    base toolset. `allowed_tools=[]` is falsy and the SDK transport skips it,
    leaving the DEFAULT toolset active — which once turned this summarisation
    call into an agentic Grep/Read loop over the substrate."""
    kwargs = _flush_extract_options_kwargs()
    tools = kwargs.get("tools")
    assert tools is not None and isinstance(tools, ast.List) and not tools.elts
