"""flush.extract_from_context — the retry ladder over the SDK harness.

Pins the 2026-09-17 contract: flush consumes `run_sdk_query` outcomes, never
the raw message stream. A fatal kind (auth / model / cli_outdated) ends the
ladder on the first attempt; a transient kind retries up to MAX_RETRIES with
the configured sleep; an is_error outcome NEVER becomes the session summary.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from core.sdk_helpers import FailureClass, SdkRunResult  # noqa: E402


@pytest.fixture
def flush_mod(monkeypatch):
    import flush

    monkeypatch.setattr(flush, "MAX_RETRIES", 3)
    monkeypatch.setattr(flush, "RETRY_DELAY", 0)
    monkeypatch.setattr(flush, "render", lambda name, **kw: f"<{name}>")
    return flush


def _outcomes(*items: SdkRunResult):
    """A fake run_sdk_query that yields the given outcomes in order and
    records every spec it was called with."""
    calls: list = []
    queue = list(items)

    async def fake(prompt, spec):  # noqa: ARG001
        calls.append(spec)
        return queue.pop(0)

    return fake, calls


def _sleeps(monkeypatch):
    slept: list[float] = []

    async def fake_sleep(s):
        slept.append(s)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    return slept


def test_success_returns_result_text(flush_mod, monkeypatch):
    fake, calls = _outcomes(SdkRunResult(result_text="## Context\nx"))
    monkeypatch.setattr(flush_mod, "run_sdk_query", fake)
    assert asyncio.run(flush_mod.extract_from_context("ctx")) == "## Context\nx"
    assert len(calls) == 1
    spec = calls[0]
    assert spec.tools == (), "flush must request an EMPTY base toolset"
    assert spec.setting_sources == ()
    assert spec.max_turns == 3


def test_fatal_kind_stops_after_first_attempt(flush_mod, monkeypatch):
    slept = _sleeps(monkeypatch)
    fake, calls = _outcomes(
        SdkRunResult(
            result_text="API Error: 400 … version 2.1.251 or newer is required",
            failure=FailureClass("cli_outdated", "API refuses the bundled CLI"),
        ),
    )
    monkeypatch.setattr(flush_mod, "run_sdk_query", fake)
    assert asyncio.run(flush_mod.extract_from_context("ctx")) is None
    assert len(calls) == 1, "a version floor does not clear on retry"
    assert slept == []


def test_transient_kind_retries_then_gives_up(flush_mod, monkeypatch):
    slept = _sleeps(monkeypatch)
    failing = SdkRunResult(failure=FailureClass("network", "ECONNRESET"))
    fake, calls = _outcomes(failing, failing, failing)
    monkeypatch.setattr(flush_mod, "run_sdk_query", fake)
    assert asyncio.run(flush_mod.extract_from_context("ctx")) is None
    assert len(calls) == 3
    assert len(slept) == 2, "sleep between attempts, not after the last"


def test_transient_kind_recovers_on_retry(flush_mod, monkeypatch):
    _sleeps(monkeypatch)
    fake, calls = _outcomes(
        SdkRunResult(failure=FailureClass("rate_limit", "429")),
        SdkRunResult(result_text="recovered"),
    )
    monkeypatch.setattr(flush_mod, "run_sdk_query", fake)
    assert asyncio.run(flush_mod.extract_from_context("ctx")) == "recovered"
    assert len(calls) == 2


def test_error_result_text_never_becomes_the_summary(flush_mod, monkeypatch):
    """SDK 0.2.x: a refused call arrives as subtype=success + is_error with the
    API's error in `result`. The harness marks it failed; flush must not
    append that text to daily/."""
    _sleeps(monkeypatch)
    refused = SdkRunResult(
        result_text="There's an issue with the selected model (x).",
        subtype="success",
        failure=FailureClass("model", "matched invalid-model pattern"),
    )
    fake, _ = _outcomes(refused)
    monkeypatch.setattr(flush_mod, "run_sdk_query", fake)
    assert asyncio.run(flush_mod.extract_from_context("ctx")) is None
