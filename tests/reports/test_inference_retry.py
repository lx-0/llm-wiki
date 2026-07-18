"""Tests for inference retryability + FailureClass-carrying errors.

The retry decision is a pure function of the structured `FailureClass.kind`
— NOT a substring match on the stringified error prose (the coupling that
`CompileOutcome` was built to kill). These tests pin:

  1. `is_inference_retryable` as a pure predicate over failure kinds.
  2. Every malformed-output raise site attaches a `schema_invalid`
     FailureClass to the InferenceError.
  3. The retry loop consults `failure.kind`, so a wording edit to an error
     message can never flip retry behaviour.
"""

from __future__ import annotations

import asyncio

import pytest

from scripts.core.sdk_helpers import FailureClass
from scripts.reports._engine.lib import inference as inf
from scripts.reports._engine.lib.inference import (
    BatchResult,
    InferenceBatch,
    InferenceError,
    SCHEMA_INVALID_KIND,
    _extract_json_from_textblocks,
    _validate_json_schema,
    is_inference_retryable,
)
from scripts.reports._engine.lib.likert import LikertItem, LikertScale


_SCALE = LikertScale(lo=0, hi=3)


def _batch() -> InferenceBatch:
    return InferenceBatch(label="all", items=(LikertItem(id="1", scale=_SCALE),))


class TestIsInferenceRetryable:
    @pytest.mark.parametrize("kind", ["cli_crash", "unknown", "schema_invalid"])
    def test_retryable_kinds(self, kind: str) -> None:
        assert is_inference_retryable(FailureClass(kind, "detail")) is True

    @pytest.mark.parametrize(
        "kind",
        ["auth", "model", "rate_limit", "network", "oom", "max_turns", "tokens_exceeded"],
    )
    def test_non_retryable_kinds(self, kind: str) -> None:
        assert is_inference_retryable(FailureClass(kind, "detail")) is False

    def test_none_failure_is_not_retryable(self) -> None:
        assert is_inference_retryable(None) is False


class TestSchemaErrorsCarryFailureClass:
    def test_not_a_json_object(self) -> None:
        with pytest.raises(InferenceError) as ei:
            _validate_json_schema([], ["1"], "all")  # type: ignore[arg-type]
        assert ei.value.failure is not None
        assert ei.value.failure.kind == SCHEMA_INVALID_KIND

    def test_missing_items_object(self) -> None:
        with pytest.raises(InferenceError) as ei:
            _validate_json_schema({"nope": {}}, ["1"], "all")
        assert ei.value.failure.kind == SCHEMA_INVALID_KIND  # type: ignore[union-attr]

    def test_omitted_items(self) -> None:
        with pytest.raises(InferenceError) as ei:
            _validate_json_schema({"items": {}}, ["1"], "all")
        assert ei.value.failure.kind == SCHEMA_INVALID_KIND  # type: ignore[union-attr]

    def test_unknown_items(self) -> None:
        with pytest.raises(InferenceError) as ei:
            _validate_json_schema({"items": {"1": {}, "99": {}}}, ["1"], "all")
        assert ei.value.failure.kind == SCHEMA_INVALID_KIND  # type: ignore[union-attr]

    def test_no_json_object(self) -> None:
        with pytest.raises(InferenceError) as ei:
            _extract_json_from_textblocks("no braces here")
        assert ei.value.failure.kind == SCHEMA_INVALID_KIND  # type: ignore[union-attr]

    def test_unbalanced_braces(self) -> None:
        with pytest.raises(InferenceError) as ei:
            _extract_json_from_textblocks('{"items": {')
        assert ei.value.failure.kind == SCHEMA_INVALID_KIND  # type: ignore[union-attr]

    def test_unparseable_json(self) -> None:
        with pytest.raises(InferenceError) as ei:
            _extract_json_from_textblocks("{not: valid, json}")
        assert ei.value.failure.kind == SCHEMA_INVALID_KIND  # type: ignore[union-attr]


class TestRetryLoopWiring:
    """The loop retries iff `is_inference_retryable(failure)` — proven by
    counting calls to the single-attempt function."""

    def _run(self, monkeypatch: pytest.MonkeyPatch, side_effects: list) -> tuple:
        calls = {"n": 0}

        async def _fake_once(*_args, **_kwargs):
            i = calls["n"]
            calls["n"] += 1
            effect = side_effects[i]
            if isinstance(effect, Exception):
                raise effect
            return effect

        async def _no_sleep(_seconds):
            return None

        monkeypatch.setattr(inf, "_infer_batch_once_async", _fake_once)
        monkeypatch.setattr(asyncio, "sleep", _no_sleep)
        return calls

    def test_retryable_failure_then_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ok = BatchResult(
            items={}, elapsed_ms=1, model_id="m", prompt_version="pv",
            cost_usd=0.0, batch_label="all",
        )
        calls = self._run(
            monkeypatch,
            [
                InferenceError("boom", failure=FailureClass(SCHEMA_INVALID_KIND, "x")),
                ok,
            ],
        )
        result = asyncio.run(
            inf.infer_batch_async(
                "prompt", _batch(), vault_cwd=None, prompt_version="pv",  # type: ignore[arg-type]
            )
        )
        assert result is ok
        assert calls["n"] == 2  # one retry consumed

    def test_non_retryable_failure_raises_immediately(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = self._run(
            monkeypatch,
            [InferenceError("auth bad", failure=FailureClass("auth", "creds"))],
        )
        with pytest.raises(InferenceError):
            asyncio.run(
                inf.infer_batch_async(
                    "prompt", _batch(), vault_cwd=None, prompt_version="pv",  # type: ignore[arg-type]
                )
            )
        assert calls["n"] == 1  # no retry for a non-retryable kind

    def test_retryable_failure_exhausts_all_attempts(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        err = InferenceError("crash", failure=FailureClass("cli_crash", "silent"))
        calls = self._run(monkeypatch, [err, err, err])
        with pytest.raises(InferenceError):
            asyncio.run(
                inf.infer_batch_async(
                    "prompt", _batch(), vault_cwd=None, prompt_version="pv",  # type: ignore[arg-type]
                )
            )
        assert calls["n"] == 3  # original + 2 retries (len(RETRY_BACKOFFS))
