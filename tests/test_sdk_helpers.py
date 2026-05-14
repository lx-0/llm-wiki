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
