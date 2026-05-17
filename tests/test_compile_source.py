"""Tests for compile_stages.compile.compile_source (M018-S02-T02).

Mirrors test_compile_reliability's SDK-mock pattern: a tmp_path-backed
vault with the heavy collaborators (render / index / facts / AGENTS.md /
prompt-budget pre-flight) stubbed out so each test reaches the SDK
``query()`` call quickly, swaps in a fake_query, and asserts the
``CompileResult`` shape.

T02 is a parallel/dormant landing — ``compile.py:compile_file`` still
contains the legacy body until T05 wires it. These tests only exercise
the new module.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import pytest


@pytest.fixture
def vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Minimal vault under tmp_path. Returns (vault_root, raw_dir).

    Redirects the path constants compile_source reads at call time, and
    stubs the context-blob readers + render() to avoid filesystem I/O on
    the engine's templates. Pre-flight stays live by default (one test
    overrides it to assert the gate fires before SDK).
    """
    from compile_stages import compile as cs_mod

    raw = tmp_path / "raw" / "notes"
    raw.mkdir(parents=True)
    (tmp_path / "knowledge").mkdir()
    (tmp_path / "AGENTS.md").write_text("# agents\n", encoding="utf-8")

    monkeypatch.setattr(cs_mod, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(cs_mod, "AGENTS_FILE", tmp_path / "AGENTS.md")
    monkeypatch.setattr(cs_mod, "KNOWLEDGE_DIR", tmp_path / "knowledge")

    monkeypatch.setattr(cs_mod, "read_wiki_index_compact", lambda: "")
    monkeypatch.setattr(cs_mod, "read_hard_facts", lambda: "")
    monkeypatch.setattr(cs_mod, "render", lambda *a, **kw: "STUB-PROMPT")
    monkeypatch.setattr(
        cs_mod, "assert_prompt_within_budget",
        lambda *a, **kw: None,
    )

    return tmp_path, raw


def _metadata(source: Path, model_id: str = "claude-opus-4-7", max_turns: int = 12):
    from compile_stages.types import CompileMetadata
    return CompileMetadata(
        source_path=source,
        compile_role="source-only",
        model_id=model_id,
        max_turns=max_turns,
        substrate_type=None,
        substrate_prompt="compile_main",
    )


def _result_message(result: str = "article body", cost: float = 0.0123):
    from claude_agent_sdk import ResultMessage
    return ResultMessage(
        subtype="success",
        duration_ms=1,
        duration_api_ms=1,
        is_error=False,
        num_turns=1,
        session_id="t",
        total_cost_usd=cost,
        usage={"input_tokens": 1000, "output_tokens": 200},
        result=result,
    )


# ── (1) Happy path — ResultMessage → CompileResult(ok) ────────────────


def test_compile_source_happy_path(vault, monkeypatch: pytest.MonkeyPatch):
    from compile_stages import compile as cs_mod
    from compile_stages.compile import compile_source

    _, raw = vault
    src = raw / "x.md"
    src.write_text("tiny content", encoding="utf-8")

    async def fake_query(*, prompt, options):  # noqa: ARG001
        yield _result_message(result="# Compiled\n\nbody", cost=0.0042)

    monkeypatch.setattr(cs_mod, "query", fake_query)

    result = asyncio.run(compile_source("tiny content", _metadata(src)))

    assert result.status == "ok", result
    assert result.article == "# Compiled\n\nbody"
    assert result.cost_usd == pytest.approx(0.0042)
    assert result.skip_reason is None
    assert result.failure_kind is None


# ── (2) kind=unknown on long-context model → skipped ──────────────────


def test_compile_source_kind_unknown_on_long_context(
    vault, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """Already on the long-context model + kind=unknown → skipped,
    not failed (consecutive-failure budget preserved)."""
    from compile_stages import compile as cs_mod
    from compile_stages.compile import compile_source

    _, raw = vault
    big = "z" * (
        cs_mod.CONFIG.limits.compile_retry_long_context_min_source_chars + 1_024
    )
    src = raw / "big-unknown.md"
    src.write_text(big, encoding="utf-8")

    monkeypatch.setattr(
        cs_mod.CONFIG.limits, "compile_skip_on_long_context_unknown", True,
    )
    monkeypatch.setattr(
        cs_mod.CONFIG.limits, "compile_per_call_timeout_s", 0,
    )
    monkeypatch.setattr(
        cs_mod.CONFIG.models, "compile_large_source_model",
        "claude-opus-4-7[1m]",
    )

    # Bypass the elapsed-time-based classifier — return kind=unknown
    # regardless of how fast the simulated crash arrived.
    import core.sdk_helpers as sdk_helpers
    from core.sdk_helpers import FailureClass

    monkeypatch.setattr(
        sdk_helpers, "classify_failure",
        lambda elapsed_s, captured_text, exc_text="": FailureClass(
            "unknown", f"simulated kind=unknown after {elapsed_s:.1f}s",
        ),
    )

    async def crashing_query(*, prompt, options):  # noqa: ARG001
        raise RuntimeError("Command failed with exit code 1")
        yield  # pragma: no cover

    monkeypatch.setattr(cs_mod, "query", crashing_query)

    # Hand compile_source the long-context model as the INITIAL model so
    # the retry-ladder won't re-fire (model == long_ctx_model after first
    # _attempt).
    metadata = _metadata(src, model_id="claude-opus-4-7[1m]")

    caplog.set_level(logging.WARNING, logger="compile")
    result = asyncio.run(compile_source(big, metadata))

    assert result.status == "skipped", result
    assert result.skip_reason == "long_context_kind_unknown"


# ── (3) max_turns failure → skipped ───────────────────────────────────


def test_compile_source_max_turns_returns_skipped(
    vault, monkeypatch: pytest.MonkeyPatch
):
    """ResultMessage(is_error=True, subtype=error_max_turns) lands as
    skip_reason=max_turns_exhausted (mirrors legacy compile_file)."""
    from compile_stages import compile as cs_mod
    from compile_stages.compile import compile_source
    from claude_agent_sdk import ResultMessage

    _, raw = vault
    src = raw / "loop.md"
    src.write_text("tiny", encoding="utf-8")

    monkeypatch.setattr(
        cs_mod.CONFIG.limits, "compile_skip_on_long_context_unknown", True,
    )
    monkeypatch.setattr(
        cs_mod.CONFIG.limits, "compile_per_call_timeout_s", 0,
    )

    async def max_turns_query(*, prompt, options):  # noqa: ARG001
        # Yield a structured error ResultMessage, then raise — mirrors the
        # bundled CLI's exit-1 behavior on subtype=error_max_turns. The
        # _attempt body reclassifies from final_result, not the exception.
        yield ResultMessage(
            subtype="error_max_turns",
            duration_ms=1,
            duration_api_ms=1,
            is_error=True,
            num_turns=12,
            session_id="t",
            total_cost_usd=0.05,
            usage={"input_tokens": 1, "output_tokens": 1},
            result="",
        )
        raise RuntimeError("Command failed with exit code 1")

    monkeypatch.setattr(cs_mod, "query", max_turns_query)

    result = asyncio.run(compile_source("tiny", _metadata(src)))

    assert result.status == "skipped", result
    assert result.skip_reason == "max_turns_exhausted"


# ── (4) pre-flight 60kb fail → skipped BEFORE SDK call ────────────────


def test_compile_source_prompt_too_large_before_sdk(
    vault, monkeypatch: pytest.MonkeyPatch
):
    """assert_prompt_within_budget raising PromptTooLargeError returns
    skipped without ever calling query()."""
    from compile_stages import compile as cs_mod
    from compile_stages.compile import compile_source
    from core.sdk_helpers import PromptTooLargeError

    _, raw = vault
    src = raw / "huge.md"
    src.write_text("x" * 100, encoding="utf-8")

    def fail_budget(*a, **kw):
        raise PromptTooLargeError(
            "compile_file huge.md exceeds budget: 1000000 chars > 800000 max"
        )

    monkeypatch.setattr(cs_mod, "assert_prompt_within_budget", fail_budget)

    sdk_called = {"flag": False}

    async def should_not_run(*, prompt, options):  # noqa: ARG001
        sdk_called["flag"] = True
        yield _result_message()

    monkeypatch.setattr(cs_mod, "query", should_not_run)

    result = asyncio.run(compile_source("x" * 100, _metadata(src)))

    assert result.status == "skipped", result
    assert result.skip_reason == "prompt_too_large"
    assert sdk_called["flag"] is False, "SDK was called despite pre-flight failure"


# ── (5) bonus — generic exception → failed ────────────────────────────


def test_compile_source_generic_exception_returns_failed(
    vault, monkeypatch: pytest.MonkeyPatch
):
    """Non-structured exception (no final ResultMessage) classifies via
    log_sdk_failure and returns CompileResult(failed) with a kind set."""
    from compile_stages import compile as cs_mod
    from compile_stages.compile import compile_source

    _, raw = vault
    src = raw / "boom.md"
    src.write_text("tiny", encoding="utf-8")

    monkeypatch.setattr(
        cs_mod.CONFIG.limits, "compile_per_call_timeout_s", 0,
    )
    # Source is too small for the long-context retry to fire — keeps the
    # test deterministic with one _attempt round.
    monkeypatch.setattr(
        cs_mod.CONFIG.limits, "compile_retry_long_context_min_source_chars",
        10_000_000,
    )

    async def boom_query(*, prompt, options):  # noqa: ARG001
        raise RuntimeError("network unreachable")
        yield  # pragma: no cover

    monkeypatch.setattr(cs_mod, "query", boom_query)

    result = asyncio.run(compile_source("tiny", _metadata(src)))

    assert result.status == "failed", result
    assert result.failure_kind is not None
