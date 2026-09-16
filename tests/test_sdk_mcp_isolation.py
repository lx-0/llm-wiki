"""Every engine SDK call must be isolated from the HOST's MCP servers.

This is the M031-S01 outage guard. From 2026-08-14 to 2026-08-25, ~99% of
session flushes died: the bundled CLI merged the host's MCP-server tool
definitions into every request, one of them ships a schema with a top-level
`oneOf`/`allOf`/`anyOf`, the API rejected it with a 400, and the CLI exited 1
with EMPTY stderr — so the only visible symptom was a retry queue growing to
234 contexts. Three other hypotheses (input size class, stale session env,
ANSI escapes) were investigated and refuted before the real cause was found.

The fix is two flags, and it had NO test: `--strict-mcp-config` plus an empty
`mcp_servers`, applied by `core.sdk_helpers.run_sdk_query` — the harness
every producer uses. `scripts/flush.py` used to construct `ClaudeAgentOptions`
directly and carry both flags itself; since 2026-09-17 it goes through the
harness (so structured API errors reach its log — the 2026-09-09→17 outage),
and the bypass-path tests below became "flush must NOT bypass the harness".
A refactor that reintroduces a direct `query()` loop in flush silently
reopens both outages, which is why these assert on the options actually
handed to the SDK and on the shape of flush's call site.
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
    {"tools": (), "setting_sources": ()},
], ids=["plain", "tools+mode", "deny-writes", "model+turns", "no-tools"])
def test_harness_isolation_holds_for_every_spec_shape(captured_options, spec_kwargs):
    """The isolation is applied after the branchy per-spec options assembly.
    A refactor that moves a branch below it, or rebuilds options_kwargs, must
    not silently drop either flag on any path."""
    sh, seen, sentinel = captured_options
    _run(sh, sentinel, **spec_kwargs)
    assert seen.get("mcp_servers") == {}
    assert "strict-mcp-config" in (seen.get("extra_args") or {})


# ── flush's call site ───────────────────────────────────────────────


def _extract_from_context_node() -> ast.AsyncFunctionDef:
    """Static read of flush.extract_from_context. Static because the point is
    to catch a REFACTOR of the call site — which a static read catches even
    if the call never runs."""
    tree = ast.parse((SCRIPTS / "flush.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "extract_from_context":
            return node
    raise AssertionError("extract_from_context not found in flush.py")


def _calls_named(node: ast.AST, name: str) -> list[ast.Call]:
    return [
        call for call in ast.walk(node)
        if isinstance(call, ast.Call) and getattr(call.func, "id", "") == name
    ]


def test_flush_goes_through_the_harness():
    """flush must not hand-roll `query()` / `ClaudeAgentOptions` again: the
    harness owns host-MCP isolation AND structured-error classification. A
    direct loop reopens the 2026-08 (MCP schema) and 2026-09 (silent API
    refusal) outages at once."""
    node = _extract_from_context_node()
    assert not _calls_named(node, "ClaudeAgentOptions"), (
        "extract_from_context builds ClaudeAgentOptions directly — route it "
        "through run_sdk_query (SdkCallSpec) instead"
    )
    assert not _calls_named(node, "query"), "extract_from_context must not call query() directly"
    assert _calls_named(node, "run_sdk_query"), "extract_from_context must call run_sdk_query"


def test_flush_still_requests_zero_tools():
    """Adjacent invariant from the same call site: `tools=()` on the spec
    emits an empty BASE toolset (`--tools ""`). `allowed_tools=()` is falsy
    and the SDK transport skips it, leaving the DEFAULT toolset active — which
    once turned this summarisation call into an agentic Grep/Read loop over
    the substrate."""
    specs = _calls_named(_extract_from_context_node(), "SdkCallSpec")
    assert specs, "extract_from_context must build an SdkCallSpec"
    kwargs = {kw.arg: kw.value for kw in specs[0].keywords if kw.arg}
    tools = kwargs.get("tools")
    assert tools is not None and isinstance(tools, ast.Tuple) and not tools.elts, (
        "flush's spec must pass tools=() — an empty base toolset, not allowed_tools"
    )


def test_harness_emits_empty_base_toolset_for_tools_spec(captured_options):
    """The harness side of the same contract: `tools=()` must reach
    ClaudeAgentOptions as `tools=[]` (truthy-check-proof list), and an unset
    spec must leave the kwarg out so the CLI default applies."""
    sh, seen, sentinel = captured_options
    _run(sh, sentinel, tools=())
    assert seen.get("tools") == []
    seen.clear()
    _run(sh, sentinel)
    assert "tools" not in seen
