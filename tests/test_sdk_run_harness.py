"""Tests for `core.sdk_helpers.run_sdk_query` — the one SDK call harness (M021 slice 1).

Fake message streams stand in for the bundled CLI. The harness owns
mechanics (options assembly, scope wiring, stall-timeout loop, cache-aware
usage extraction on BOTH bases, LEDGER recording, failure classification);
these tests pin exactly those behaviours:

  1. cache-inclusive LEDGER basis vs uncached budget basis (DECISIONS
     2026-06-02 dual-basis rule) — including the ResultMessage-preferred /
     per-turn-fallback distinction that had drifted between compile and
     dream.
  2. every outcome records to LEDGER (success, structured error, timeout,
     crash) — partial usage from a failed call is still real spend.
  3. scope wiring: write_scope → PreToolUse hook shape (or legacy globs
     when the callback-gate flag is off); deny_all_writes → can_use_tool
     gate + streaming prompt.
  4. failure classification parity with the hand-rolled loops it replaced.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import pytest

from core.sdk_helpers import SdkCallSpec, WriteScope, run_sdk_query
from core.usage import UsageLedger

log = logging.getLogger("test-harness")


# ── message factories ─────────────────────────────────────────────────


def _assistant(usage: dict | None, text: str = "thinking"):
    from claude_agent_sdk import AssistantMessage, TextBlock
    return AssistantMessage(content=[TextBlock(text=text)], model="m", usage=usage)


def _result(
    result: str = "final answer",
    cost: float = 0.5,
    usage: dict | None = None,
    *,
    is_error: bool = False,
    subtype: str = "success",
    num_turns: int = 1,
):
    from claude_agent_sdk import ResultMessage
    return ResultMessage(
        subtype=subtype,
        duration_ms=1,
        duration_api_ms=1,
        is_error=is_error,
        num_turns=num_turns,
        session_id="t",
        total_cost_usd=cost,
        usage=usage,
        result=result,
    )


def _spec(**overrides) -> SdkCallSpec:
    defaults = dict(label="test_call", logger=log, model="claude-test-model")
    defaults.update(overrides)
    return SdkCallSpec(**defaults)


@pytest.fixture
def ledger(monkeypatch: pytest.MonkeyPatch) -> UsageLedger:
    """Fresh ledger swapped in for the process-global one. The harness
    imports LEDGER at call time, so the swap is visible."""
    import core.usage as usage_mod
    fresh = UsageLedger()
    monkeypatch.setattr(usage_mod, "LEDGER", fresh)
    return fresh


# ── 1. dual-basis token accounting ────────────────────────────────────


def test_result_usage_preferred_cache_inclusive(ledger: UsageLedger):
    """ResultMessage.usage (authoritative cumulative) wins over the
    per-turn sum; input_tokens is the cache-inclusive total."""
    usage = {
        "input_tokens": 12,
        "cache_creation_input_tokens": 40_000,
        "cache_read_input_tokens": 1_500,
        "output_tokens": 90,
    }

    async def fake_query(*, prompt, options):  # noqa: ARG001
        yield _assistant({"input_tokens": 5, "output_tokens": 2})
        yield _result(usage=usage, cost=0.79)

    result = asyncio.run(run_sdk_query("p" * 100, _spec(), query_fn=fake_query))

    assert result.ok
    assert result.input_tokens == 12 + 40_000 + 1_500
    assert result.output_tokens == 90
    assert result.cost_usd == pytest.approx(0.79)
    # LEDGER got the cache-inclusive total, keyed by (claude, model).
    totals = ledger.totals()
    u = totals[("claude", "claude-test-model")]
    assert u.input_tokens == 41_512
    assert u.output_tokens == 90
    assert u.calls == 1


def test_per_turn_fallback_is_cache_inclusive_but_budget_basis_is_uncached(
    ledger: UsageLedger,
):
    """The exact compile↔dream drift point: when the ResultMessage carries
    no usage, the LEDGER fallback accumulates the CACHE-INCLUSIVE per-turn
    sum (dream's fixed behaviour), while the uncached_* fields keep the raw
    per-turn sum for budget guards (compile's deliberate basis)."""
    turn_usage = {
        "input_tokens": 10,
        "cache_creation_input_tokens": 1_000,
        "cache_read_input_tokens": 500,
        "output_tokens": 5,
    }

    async def fake_query(*, prompt, options):  # noqa: ARG001
        yield _assistant(turn_usage)
        yield _assistant(turn_usage)
        yield _result(usage=None, cost=0.1)

    result = asyncio.run(run_sdk_query("p", _spec(), query_fn=fake_query))

    assert result.ok
    assert result.input_tokens == 2 * (10 + 1_000 + 500)   # cache-inclusive fallback
    assert result.output_tokens == 10
    assert result.uncached_input_tokens == 20              # raw per-turn (budget basis)
    assert result.uncached_output_tokens == 10
    assert ledger.totals()[("claude", "claude-test-model")].input_tokens == 3_020


def test_assistant_text_and_result_text_both_captured(ledger: UsageLedger):
    async def fake_query(*, prompt, options):  # noqa: ARG001
        yield _assistant(None, text='{"items": ')
        yield _assistant(None, text='{}}')
        yield _result(result="final", usage={"input_tokens": 1, "output_tokens": 1})

    result = asyncio.run(run_sdk_query("p", _spec(), query_fn=fake_query))
    assert result.assistant_text == '{"items": {}}'
    assert result.result_text == "final"
    assert result.message_count == 3


# ── 2. LEDGER coverage on failure paths ───────────────────────────────


def test_timeout_records_partial_usage_and_classifies(ledger: UsageLedger):
    async def hanging_query(*, prompt, options):  # noqa: ARG001
        yield _assistant({"input_tokens": 7, "cache_creation_input_tokens": 100,
                          "output_tokens": 3})
        await asyncio.sleep(60)

    result = asyncio.run(
        run_sdk_query("p", _spec(stall_timeout_s=0.05), query_fn=hanging_query)
    )

    assert result.failure is not None
    assert result.failure.kind == "timeout"
    assert result.message_count == 1
    # Partial per-turn usage still lands in the ledger (real spend).
    u = ledger.totals()[("claude", "claude-test-model")]
    assert u.input_tokens == 107
    assert u.calls == 1


def test_generic_exception_classified_and_recorded(ledger: UsageLedger):
    async def boom_query(*, prompt, options):  # noqa: ARG001
        raise RuntimeError("Command failed with exit code 1")
        yield  # pragma: no cover

    result = asyncio.run(run_sdk_query("p", _spec(), query_fn=boom_query))

    assert result.failure is not None
    # Fast fail with empty stderr → cli_crash per classify_failure.
    assert result.failure.kind == "cli_crash"
    assert isinstance(result.exc, RuntimeError)
    assert ledger.totals()[("claude", "claude-test-model")].calls == 1


def test_structured_error_max_turns(ledger: UsageLedger):
    """ResultMessage(is_error, subtype=error_max_turns) then raise — the
    bundled CLI's exit-1 shape. Kind comes from the structured payload,
    LEDGER gets the authoritative cache-inclusive usage."""
    async def max_turns_query(*, prompt, options):  # noqa: ARG001
        yield _result(
            result="", cost=0.05, is_error=True, subtype="error_max_turns",
            num_turns=12,
            usage={"input_tokens": 3, "cache_creation_input_tokens": 900,
                   "output_tokens": 4},
        )
        raise RuntimeError("Command failed with exit code 1")

    result = asyncio.run(run_sdk_query("p", _spec(), query_fn=max_turns_query))

    assert result.failure is not None
    assert result.failure.kind == "max_turns"
    assert "12 turns" in result.failure.detail
    assert result.subtype == "error_max_turns"
    assert result.input_tokens == 903
    assert result.cost_usd == pytest.approx(0.05)
    assert ledger.totals()[("claude", "claude-test-model")].input_tokens == 903


def test_structured_error_without_raise_still_classified(ledger: UsageLedger):
    """A clean generator exit with is_error=True must not masquerade as ok."""
    async def error_query(*, prompt, options):  # noqa: ARG001
        yield _result(
            result="", cost=0.0, is_error=True, subtype="error_max_turns",
            num_turns=8, usage={"input_tokens": 1, "output_tokens": 1},
        )

    result = asyncio.run(run_sdk_query("p", _spec(), query_fn=error_query))
    assert result.failure is not None
    assert result.failure.kind == "max_turns"


def test_default_model_records_under_claude_provider(ledger: UsageLedger):
    """model=None (CLI default) must not fall into the ollama provider
    bucket via provider_for_model('') — the harness is Claude-side by
    definition and records provider explicitly."""
    async def fake_query(*, prompt, options):  # noqa: ARG001
        yield _result(usage={"input_tokens": 10, "output_tokens": 5})

    asyncio.run(run_sdk_query("p", _spec(model=None), query_fn=fake_query))
    assert ("claude", "(default)") in ledger.totals()


def test_record_usage_false_skips_ledger(ledger: UsageLedger):
    async def fake_query(*, prompt, options):  # noqa: ARG001
        yield _result(usage={"input_tokens": 10, "output_tokens": 5})

    asyncio.run(run_sdk_query("p", _spec(record_usage=False), query_fn=fake_query))
    assert ledger.is_empty()


# ── 3. scope wiring ───────────────────────────────────────────────────


def _capture_options(captured: dict):
    async def fake_query(*, prompt, options):
        captured["prompt"] = prompt
        captured["options"] = options
        yield _result(usage={"input_tokens": 1, "output_tokens": 1})
    return fake_query


def test_write_scope_wires_pretooluse_hook(ledger: UsageLedger, tmp_path: Path):
    captured: dict = {}
    spec = _spec(
        allowed_tools=("Read", "Glob", "Grep", "Write", "Edit"),
        write_scope=WriteScope(roots=(tmp_path / "knowledge",)),
    )
    asyncio.run(run_sdk_query("p", spec, query_fn=_capture_options(captured)))

    options = captured["options"]
    assert options.permission_mode == "default"
    assert "Write" in options.allowed_tools and "Edit" in options.allowed_tools
    assert "PreToolUse" in options.hooks
    matcher = options.hooks["PreToolUse"][0]
    assert matcher.matcher == "Write|Edit"
    # String prompt — hooks do not require the streaming envelope.
    assert captured["prompt"] == "p"


def test_write_scope_legacy_shape_when_gate_flag_off(
    ledger: UsageLedger, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from core.config import CONFIG
    monkeypatch.setattr(CONFIG.features, "compile_callback_gate", False)

    captured: dict = {}
    legacy = ("Read", "Glob", "Grep", "Write(knowledge/**)", "Edit(knowledge/**)")
    spec = _spec(
        allowed_tools=("Read", "Glob", "Grep", "Write", "Edit"),
        write_scope=WriteScope(
            roots=(tmp_path / "knowledge",), legacy_allowed_tools=legacy,
        ),
    )
    asyncio.run(run_sdk_query("p", spec, query_fn=_capture_options(captured)))

    options = captured["options"]
    assert options.allowed_tools == list(legacy)
    assert options.permission_mode == "acceptEdits"
    assert not options.hooks


def test_write_scope_hook_shape_ignores_flag_without_legacy_tools(
    ledger: UsageLedger, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Sites without a legacy fallback (correct_apply/reconcile) keep the
    hook shape even when the compile rollback flag is off."""
    from core.config import CONFIG
    monkeypatch.setattr(CONFIG.features, "compile_callback_gate", False)

    captured: dict = {}
    spec = _spec(
        allowed_tools=("Read", "Write", "Edit"),
        write_scope=WriteScope(roots=(tmp_path / "knowledge",)),
    )
    asyncio.run(run_sdk_query("p", spec, query_fn=_capture_options(captured)))
    assert "PreToolUse" in captured["options"].hooks
    assert captured["options"].permission_mode == "default"


def test_deny_all_writes_wires_gate_and_streaming_prompt(ledger: UsageLedger):
    captured: dict = {}
    spec = _spec(
        allowed_tools=("Read", "Glob", "Grep"),
        disallowed_tools=("Write", "Edit", "NotebookEdit"),
        deny_all_writes=True,
        setting_sources=("project",),
    )
    asyncio.run(run_sdk_query("hello", spec, query_fn=_capture_options(captured)))

    options = captured["options"]
    assert options.can_use_tool is not None
    assert options.permission_mode == "default"
    assert options.disallowed_tools == ["Write", "Edit", "NotebookEdit"]
    assert options.setting_sources == ["project"]

    # The can_use_tool contract requires a streaming prompt.
    async def _collect(stream):
        return [m async for m in stream]
    msgs = asyncio.run(_collect(captured["prompt"]))
    assert msgs == [
        {"type": "user", "message": {"role": "user", "content": "hello"}}
    ]

    # And the gate itself denies writes anywhere.
    async def _deny_check():
        return await options.can_use_tool("Write", {"file_path": "/tmp/x.md"}, None)
    assert asyncio.run(_deny_check()).behavior == "deny"


def test_plain_spec_passes_policy_through(ledger: UsageLedger, tmp_path: Path):
    captured: dict = {}
    spec = _spec(
        cwd=tmp_path,
        max_turns=15,
        system_prompt={"type": "preset", "preset": "claude_code"},
        allowed_tools=("Read", "Glob", "Grep"),
        permission_mode="acceptEdits",
    )
    asyncio.run(run_sdk_query("p", spec, query_fn=_capture_options(captured)))

    options = captured["options"]
    assert options.cwd == str(tmp_path)
    assert options.max_turns == 15
    assert options.system_prompt == {"type": "preset", "preset": "claude_code"}
    assert options.allowed_tools == ["Read", "Glob", "Grep"]
    assert options.permission_mode == "acceptEdits"
    assert options.model == "claude-test-model"


# ── 4. no ResultMessage at all ────────────────────────────────────────


def test_stream_without_result_message_is_ok_with_fallback_usage(
    ledger: UsageLedger,
):
    """Stream ends cleanly with only AssistantMessages: not a failure
    (parity with the legacy loops), usage from the per-turn fallback."""
    async def fake_query(*, prompt, options):  # noqa: ARG001
        yield _assistant({"input_tokens": 4, "output_tokens": 2}, text="partial")

    result = asyncio.run(run_sdk_query("p", _spec(), query_fn=fake_query))
    assert result.ok
    assert result.result_text == ""
    assert result.assistant_text == "partial"
    assert result.input_tokens == 4
    assert result.num_turns == 0
