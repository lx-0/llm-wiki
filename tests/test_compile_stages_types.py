"""Tests for compile_stages.types (M018-S02-T01).

CompileResult + CompileMetadata dataclasses. Mirror ProducerResult shape
(status: ok/skipped/failed, reason, cost) so end-of-run aggregation reads
both seam outputs uniformly.
"""

from __future__ import annotations

from pathlib import Path

import pytest


# ── CompileResult ────────────────────────────────────────────────────


def test_compile_result_defaults():
    from compile_stages.types import CompileResult

    r = CompileResult(status="ok")
    assert r.status == "ok"
    assert r.article is None
    assert r.frontmatter_extra == {}
    assert r.cost_usd == 0.0
    assert r.skip_reason is None
    assert r.failure_kind is None
    assert r.input_tokens == 0
    assert r.output_tokens == 0


def test_compile_result_status_values():
    """All three documented statuses construct cleanly."""
    from compile_stages.types import CompileResult

    for status in ("ok", "skipped", "failed"):
        CompileResult(status=status)  # type: ignore[arg-type]


def test_compile_result_ok_with_article():
    from compile_stages.types import CompileResult

    r = CompileResult(
        status="ok",
        article="# Test\n\nbody",
        frontmatter_extra={"compiled_from": ["raw/notes/x.md"]},
        cost_usd=0.0123,
        input_tokens=1500,
        output_tokens=300,
    )
    assert r.article == "# Test\n\nbody"
    assert r.frontmatter_extra["compiled_from"] == ["raw/notes/x.md"]
    assert r.cost_usd == 0.0123


def test_compile_result_skipped_with_reason():
    from compile_stages.types import CompileResult

    r = CompileResult(status="skipped", skip_reason="prompt_too_large")
    assert r.status == "skipped"
    assert r.skip_reason == "prompt_too_large"
    assert r.article is None


def test_compile_result_failed_with_kind():
    from compile_stages.types import CompileResult

    r = CompileResult(status="failed", failure_kind="rate_limit")
    assert r.status == "failed"
    assert r.failure_kind == "rate_limit"


def test_compile_result_is_frozen():
    from compile_stages.types import CompileResult

    r = CompileResult(status="ok")
    with pytest.raises((AttributeError, Exception)):
        r.status = "failed"  # type: ignore[misc]


# ── CompileMetadata ──────────────────────────────────────────────────


def test_compile_metadata_required_fields(tmp_path):
    from compile_stages.types import CompileMetadata

    m = CompileMetadata(
        source_path=tmp_path / "raw" / "x.md",
        compile_role="source-only",
        model_id="claude-opus-4-7",
        max_turns=12,
        substrate_type=None,
    )
    assert m.source_path == tmp_path / "raw" / "x.md"
    assert m.compile_role == "source-only"
    assert m.model_id == "claude-opus-4-7"
    assert m.max_turns == 12
    assert m.substrate_type is None


def test_compile_metadata_with_substrate_type(tmp_path):
    from compile_stages.types import CompileMetadata

    m = CompileMetadata(
        source_path=tmp_path / "raw" / "transcripts" / "x.md",
        compile_role="source-only",
        model_id="claude-haiku-4-5-20251001",
        max_turns=20,
        substrate_type="daily-digest",
    )
    assert m.substrate_type == "daily-digest"


def test_compile_metadata_is_frozen(tmp_path):
    from compile_stages.types import CompileMetadata

    m = CompileMetadata(
        source_path=tmp_path / "x.md",
        compile_role="source-only",
        model_id="claude-opus-4-7",
        max_turns=12,
        substrate_type=None,
    )
    with pytest.raises((AttributeError, Exception)):
        m.model_id = "other"  # type: ignore[misc]


def test_compile_metadata_compile_role_values(tmp_path):
    """compile_role accepts the three M007 axis values."""
    from compile_stages.types import CompileMetadata

    for role in ("source-only", "source-and-final", "final-only"):
        CompileMetadata(
            source_path=tmp_path / "x.md",
            compile_role=role,  # type: ignore[arg-type]
            model_id="claude-opus-4-7",
            max_turns=12,
            substrate_type=None,
        )
