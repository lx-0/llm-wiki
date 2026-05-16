"""compile.py reliability bundle — 60kb size warn / per-call timeout / [1m] skip.

Three independent fixes that together make Phase-2 bulk migrations survivable.
Each test mocks the Claude Agent SDK `query()` and the heaviest of compile's
file-system dependencies (prompts/render, AGENTS.md, hard facts, knowledge
index) so the tests run offline and in <2s.

Specs:
- `.ytstack/backlog/compile-60kb-plus-silent-fail.md`
- `.ytstack/backlog/compile-per-call-timeout.md`
- `.ytstack/backlog/compile-already-on-1m-fallback.md`
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import AsyncIterator

import pytest


# ── shared scaffolding ────────────────────────────────────────────────


@pytest.fixture
def vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Minimal vault under tmp_path. Returns (vault_root, raw_dir).

    compile.py's compile_file does a long chain of FS reads. We redirect
    every path the function touches to tmp_path equivalents and stub out
    the heavy helpers (render, read_wiki_index_compact, read_hard_facts,
    assert_prompt_within_budget).
    """
    import compile as compile_mod

    raw = tmp_path / "raw" / "notes"
    raw.mkdir(parents=True)
    (tmp_path / "knowledge").mkdir()
    (tmp_path / "AGENTS.md").write_text("# agents\n", encoding="utf-8")

    # Redirect path constants the function reads at call time.
    monkeypatch.setattr(compile_mod, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(compile_mod, "AGENTS_FILE", tmp_path / "AGENTS.md")

    # Stub the heavy collaborators so the function reaches _attempt fast.
    monkeypatch.setattr(compile_mod, "read_wiki_index_compact", lambda: "")
    monkeypatch.setattr(compile_mod, "read_hard_facts", lambda: "")
    monkeypatch.setattr(compile_mod, "render", lambda *a, **kw: "STUB-PROMPT")
    # Bypass the prompt-budget pre-flight (we feed huge sources deliberately).
    monkeypatch.setattr(
        compile_mod, "assert_prompt_within_budget",
        lambda *a, **kw: None,
    )

    return tmp_path, raw


def _write_source(raw: Path, name: str, content: str) -> Path:
    p = raw / name
    p.write_text(content, encoding="utf-8")
    return p


# ── Fix 1: 60 KB+ INFO size warning ───────────────────────────────────


def test_size_warning_fires_at_60kb_threshold(
    vault, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """Source ≥ 60_000 chars emits an INFO 'size warning' line BEFORE the SDK call."""
    import compile as compile_mod
    from claude_agent_sdk import ResultMessage

    _, raw = vault
    big = "x" * 60_500
    source = _write_source(raw, "big.md", big)

    async def fake_query(*, prompt, options):  # noqa: ARG001
        yield ResultMessage(
            subtype="success",
            duration_ms=1, duration_api_ms=1,
            is_error=False, num_turns=1, session_id="t",
            total_cost_usd=0.0, usage={"input_tokens": 1, "output_tokens": 1},
            result="ok",
        )

    monkeypatch.setattr(compile_mod, "query", fake_query)

    caplog.set_level(logging.INFO, logger="compile")
    asyncio.run(compile_mod.compile_file(source, force=True))

    matched = [
        r for r in caplog.records
        if "size warning" in r.getMessage() and "60500" in r.getMessage()
    ]
    assert matched, (
        "Expected an INFO 'size warning' line citing the source size; got: "
        + " | ".join(r.getMessage() for r in caplog.records)
    )
    assert matched[0].levelname == "INFO"


def test_size_warning_silent_below_60kb(
    vault, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """Sources below the threshold get no size-warning line."""
    import compile as compile_mod
    from claude_agent_sdk import ResultMessage

    _, raw = vault
    small = "y" * 50_000  # well below 60 KB
    source = _write_source(raw, "small.md", small)

    async def fake_query(*, prompt, options):  # noqa: ARG001
        yield ResultMessage(
            subtype="success",
            duration_ms=1, duration_api_ms=1,
            is_error=False, num_turns=1, session_id="t",
            total_cost_usd=0.0, usage={"input_tokens": 1, "output_tokens": 1},
            result="ok",
        )

    monkeypatch.setattr(compile_mod, "query", fake_query)
    caplog.set_level(logging.INFO, logger="compile")
    asyncio.run(compile_mod.compile_file(source, force=True))

    assert not any("size warning" in r.getMessage() for r in caplog.records)


# ── Fix 2: per-call timeout → _skipped ────────────────────────────────


def test_per_call_timeout_returns_skipped(
    vault, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """A query() that stalls past compile_per_call_timeout_s returns _skipped."""
    import compile as compile_mod

    _, raw = vault
    source = _write_source(raw, "stall.md", "tiny content")

    # Override the timeout knob to a tight value so the test runs in <1 s.
    monkeypatch.setattr(
        compile_mod.CONFIG.limits, "compile_per_call_timeout_s", 1,
    )

    async def hanging_query(*, prompt, options):  # noqa: ARG001
        # Sleep longer than the timeout, never emit a message.
        await asyncio.sleep(60)
        yield  # pragma: no cover

    monkeypatch.setattr(compile_mod, "query", hanging_query)

    caplog.set_level(logging.WARNING, logger="compile")
    result = asyncio.run(compile_mod.compile_file(source, force=True))

    assert result == {"_skipped": "compile_per_call_timeout"}, result
    # WARNING line surfaces the hang for the operator.
    assert any(
        "per-call timeout" in r.getMessage() and r.levelname == "WARNING"
        for r in caplog.records
    ), [r.getMessage() for r in caplog.records]


def test_per_call_timeout_disabled_with_zero(
    vault, monkeypatch: pytest.MonkeyPatch
):
    """Setting compile_per_call_timeout_s=0 disables the wait_for wrap."""
    import compile as compile_mod
    from claude_agent_sdk import ResultMessage

    _, raw = vault
    source = _write_source(raw, "fast.md", "tiny")

    monkeypatch.setattr(
        compile_mod.CONFIG.limits, "compile_per_call_timeout_s", 0,
    )

    async def fast_query(*, prompt, options):  # noqa: ARG001
        # Brief sleep (not asyncio.sleep so we don't accidentally re-engage
        # timeout — though with timeout=0 the path bypasses wait_for).
        yield ResultMessage(
            subtype="success",
            duration_ms=1, duration_api_ms=1,
            is_error=False, num_turns=1, session_id="t",
            total_cost_usd=0.0, usage={"input_tokens": 1, "output_tokens": 1},
            result="ok",
        )

    monkeypatch.setattr(compile_mod, "query", fast_query)
    result = asyncio.run(compile_mod.compile_file(source, force=True))
    # Success path: dict with cost_usd, NOT _skipped.
    assert result is not None
    assert "_skipped" not in result, result


# ── Fix 3: kind=unknown already-on-[1m] survives as _skipped ─────────


def test_kind_unknown_on_long_context_skips(
    vault, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """When [1m] retry also fails kind=unknown, compile_file returns _skipped
    (not _failure) so the consecutive-failure budget is preserved."""
    import compile as compile_mod

    _, raw = vault
    # Make the source big enough to clear compile_retry_long_context_min_source_chars
    # so the long-context retry actually engages.
    big = "z" * (compile_mod.CONFIG.limits.compile_retry_long_context_min_source_chars + 1_024)
    source = _write_source(raw, "big-unknown.md", big)

    # Ensure both knobs are on so the retry-then-skip path runs.
    monkeypatch.setattr(
        compile_mod.CONFIG.limits, "compile_retry_long_context_on_unknown", True,
    )
    monkeypatch.setattr(
        compile_mod.CONFIG.limits, "compile_skip_on_long_context_unknown", True,
    )
    monkeypatch.setattr(
        compile_mod.CONFIG.limits, "compile_failure_backoff_s", 0,
    )
    # Disable per-call timeout so the simulated SDK error is what fails,
    # not the test scaffold's tight timeout.
    monkeypatch.setattr(
        compile_mod.CONFIG.limits, "compile_per_call_timeout_s", 0,
    )
    # Force a long-context model id so the retry path can fire.
    monkeypatch.setattr(
        compile_mod.CONFIG.models, "compile_large_source_model",
        "claude-opus-4-7[1m]",
    )

    # Patch the SDK classifier so we don't need to wait >5s in real time
    # to land in `kind=unknown` (the classifier uses elapsed < 5s as a
    # cli_crash signal — see scripts/core/sdk_helpers.py:classify_failure).
    import core.sdk_helpers as sdk_helpers
    from core.sdk_helpers import FailureClass

    def fake_classify(elapsed_s, captured_text, exc_text=""):  # noqa: ARG001
        return FailureClass(
            "unknown",
            f"simulated kind=unknown after {elapsed_s:.1f}s",
        )

    monkeypatch.setattr(sdk_helpers, "classify_failure", fake_classify)

    async def crashing_query(*, prompt, options):  # noqa: ARG001
        # Bundled-CLI exit-1 with no ResultMessage. classify_failure (patched
        # above) turns it into kind=unknown — the silent-fail signature.
        raise RuntimeError("Command failed with exit code 1")
        yield  # pragma: no cover

    monkeypatch.setattr(compile_mod, "query", crashing_query)
    caplog.set_level(logging.WARNING, logger="compile")
    result = asyncio.run(compile_mod.compile_file(source, force=True))

    assert result == {"_skipped": "kind_unknown_on_long_context"}, result
    # Operator-visible WARNING explains the skip.
    assert any(
        "kind=unknown on long-context model" in r.getMessage()
        for r in caplog.records
    ), [r.getMessage() for r in caplog.records]


# ── config knob present + migration entry present ────────────────────


def test_compile_per_call_timeout_config_knob_present():
    """The knob lives in the Limits dataclass with the documented default."""
    from core.config import Limits
    lim = Limits()
    assert hasattr(lim, "compile_per_call_timeout_s")
    assert lim.compile_per_call_timeout_s == 600


def test_compile_per_call_timeout_in_migration_additions():
    """Same-commit migration: the knob is wired into KEY_ADDITIONS so existing
    operator vaults pick it up via `wiki update` (CLAUDE.md hard rule)."""
    from migrations.migrate_config_keys import KEY_ADDITIONS
    assert "compile_per_call_timeout_s" in KEY_ADDITIONS["limits"]
    assert KEY_ADDITIONS["limits"]["compile_per_call_timeout_s"] == 600
