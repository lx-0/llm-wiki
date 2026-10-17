"""flush.extract_from_context — the retry ladder over the SDK harness.

Pins the 2026-09-17 contract: flush consumes `run_sdk_query` outcomes, never
the raw message stream. A fatal kind (auth / model / cli_outdated) ends the
ladder on the first attempt; a transient kind retries up to MAX_RETRIES with
the configured sleep; an is_error outcome NEVER becomes the session summary.
"""

from __future__ import annotations

import asyncio
import logging

import pytest

from core.sdk_helpers import FailureClass, SdkRunResult


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

    async def fake(prompt, spec):
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
        SdkRunResult(result_text="## Context\nrecovered"),
    )
    monkeypatch.setattr(flush_mod, "run_sdk_query", fake)
    assert asyncio.run(flush_mod.extract_from_context("ctx")) == "## Context\nrecovered"
    assert len(calls) == 2


_ECHO = "## Assistant\n\nRunning the tests now.\n\n[Bash] uv run pytest -q\n\n## User\n\nok\n"


def test_a_reply_that_continues_the_transcript_is_not_a_summary(flush_mod, monkeypatch):
    """The extractor sometimes answers in the session's own voice: `## User` /
    `## Assistant` turns with tool lines, the context's format, instead of the distill.
    46 such blocks sit in the live lxw daily/ (45 Claude Code, 1 Codex; last 2026-09-04),
    permanent because the context is deleted after a write (M034-S06-T07). An echo is a
    failed attempt."""
    _sleeps(monkeypatch)
    fake, calls = _outcomes(*(SdkRunResult(result_text=_ECHO) for _ in range(3)))
    monkeypatch.setattr(flush_mod, "run_sdk_query", fake)
    assert asyncio.run(flush_mod.extract_from_context("ctx")) is None
    assert len(calls) == 3


def test_an_echo_is_retried_and_a_distill_wins(flush_mod, monkeypatch):
    _sleeps(monkeypatch)
    fake, calls = _outcomes(
        SdkRunResult(result_text=_ECHO), SdkRunResult(result_text="## Context\nthe distill")
    )
    monkeypatch.setattr(flush_mod, "run_sdk_query", fake)
    assert asyncio.run(flush_mod.extract_from_context("ctx")) == "## Context\nthe distill"
    assert len(calls) == 2


def test_a_reply_without_sections_answered_the_conversation(flush_mod, monkeypatch):
    """The other echo: the extractor answers the session's last message in the assistant's
    voice, no section at all — "Ehrlich: …", "Du hast völlig recht, und das ist mein
    Fehler …" (live daily/2026-09-05). Written, it would read as the session's finding."""
    _sleeps(monkeypatch)
    reply = SdkRunResult(result_text="Du hast völlig recht, und das ist mein Fehler.")
    fake, calls = _outcomes(reply, reply, reply)
    monkeypatch.setattr(flush_mod, "run_sdk_query", fake)
    assert asyncio.run(flush_mod.extract_from_context("ctx")) is None
    assert len(calls) == 3


def test_a_rejected_reply_is_named_where_the_doctor_reads_it(flush_mod, monkeypatch, caplog):
    """`wiki doctor` names the newest classified flush failure from flush-errors.log, in
    the harness's `flush_extract … kind=` shape. The harness logged these calls a success."""
    from core.health.pipeline import _RE_FLUSH_FAILURE_KIND

    _sleeps(monkeypatch)
    replies = (SdkRunResult(result_text="Ehrlich: mein Fehler."), SdkRunResult(result_text=_ECHO))
    fake, _ = _outcomes(*replies, replies[0])
    monkeypatch.setattr(flush_mod, "run_sdk_query", fake)
    with caplog.at_level(logging.WARNING, logger="flush"):
        asyncio.run(flush_mod.extract_from_context("ctx"))
    named = [m.group(1) for r in caplog.records if (m := _RE_FLUSH_FAILURE_KIND.search(r.message))]
    assert named == ["no_sections", "transcript_echo", "no_sections"]


def test_an_empty_reply_is_a_failed_attempt(flush_mod, monkeypatch):
    _sleeps(monkeypatch)
    fake, calls = _outcomes(SdkRunResult(result_text=""), SdkRunResult(result_text="## Context\nx"))
    monkeypatch.setattr(flush_mod, "run_sdk_query", fake)
    assert asyncio.run(flush_mod.extract_from_context("ctx")) == "## Context\nx"
    assert len(calls) == 2


def test_sections_at_h1_are_a_distill(flush_mod, monkeypatch):
    """The model answers at H1 as often as at the prompt's H2 (live since 2026-09-21)."""
    fake, _ = _outcomes(SdkRunResult(result_text="# Context\nx\n\n# Decisions\n- y"))
    monkeypatch.setattr(flush_mod, "run_sdk_query", fake)
    assert asyncio.run(flush_mod.extract_from_context("ctx")) == "# Context\nx\n\n# Decisions\n- y"


@pytest.mark.parametrize("reply", ["NOTHING_TO_SAVE", "  `NOTHING_TO_SAVE`\n"])
def test_nothing_to_save_is_an_answer_not_a_failure(flush_mod, monkeypatch, reply):
    """A conversation with nothing worth keeping (live: "No extractable content — the
    conversation contains only system context …", daily/2026-08-30) has one reply. It is
    not retried: as a failure it would sit in the retry archive for good."""
    slept = _sleeps(monkeypatch)
    fake, calls = _outcomes(SdkRunResult(result_text=reply))
    monkeypatch.setattr(flush_mod, "run_sdk_query", fake)
    assert asyncio.run(flush_mod.extract_from_context("ctx")) == flush_mod.NOTHING_TO_SAVE
    assert len(calls) == 1
    assert slept == []


def test_the_prompt_names_the_nothing_to_save_reply():
    import flush
    from core.prompts import render

    assert flush.NOTHING_TO_SAVE in render("flush_extract", context="x")


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
