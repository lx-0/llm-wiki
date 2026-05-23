"""M026-S01-T01: CompileOutcome + Route union types.

Pure additive data types — no engine wiring. Mirrors test_compile_stages_types
(import inside each test, frozen-ness check).
"""
from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest


# ── CompileOutcome ───────────────────────────────────────────────────

def test_compile_outcome_defaults():
    from compile_stages.types import CompileOutcome

    o = CompileOutcome(status="compiled")
    assert o.status == "compiled"
    assert o.skip_reason is None
    assert o.failure_kind is None
    assert o.failure_detail is None
    assert o.ingest_hash is False
    assert o.cost_usd == 0.0
    assert o.input_tokens == 0
    assert o.output_tokens == 0


def test_compile_outcome_skipped_with_ingest_hash():
    from compile_stages.types import CompileOutcome

    o = CompileOutcome(status="skipped", skip_reason="dry_run", ingest_hash=True)
    assert o.status == "skipped"
    assert o.skip_reason == "dry_run"
    assert o.ingest_hash is True


def test_compile_outcome_failed_with_kind():
    from compile_stages.types import CompileOutcome

    o = CompileOutcome(status="failed", failure_kind="rate_limit", failure_detail="429")
    assert o.failure_kind == "rate_limit"
    assert o.failure_detail == "429"


def test_compile_outcome_is_frozen():
    from compile_stages.types import CompileOutcome

    o = CompileOutcome(status="compiled")
    with pytest.raises(FrozenInstanceError):
        o.status = "failed"  # type: ignore[misc]


# ── Route union ──────────────────────────────────────────────────────

def test_route_skip():
    from compile_stages.route import Skip

    r = Skip(reason="empty")
    assert r.reason == "empty"


def test_route_index_only():
    from compile_stages.route import IndexOnly

    r = IndexOnly(title="My Strategy", wikilinks=("a", "b"))
    assert r.title == "My Strategy"
    assert r.wikilinks == ("a", "b")


def test_route_health_stub():
    from compile_stages.route import HealthStub

    r = HealthStub()
    assert isinstance(r, HealthStub)


def test_route_compile_carries_metadata_and_classification():
    from compile_stages.classify import ClassifyResult
    from compile_stages.route import Compile
    from compile_stages.types import CompileMetadata

    meta = CompileMetadata(
        source_path=Path("raw/notes/x.md"),
        compile_role="source-only",
        model_id="claude-haiku-4-5-20251001",
        max_turns=12,
        substrate_type=None,
    )
    cls = ClassifyResult(kind="single", chunks=["body"])
    r = Compile(metadata=meta, classification=cls)
    assert r.metadata.model_id == "claude-haiku-4-5-20251001"
    assert r.classification.kind == "single"


def test_route_variants_are_frozen():
    from compile_stages.route import Skip

    r = Skip(reason="empty")
    with pytest.raises(FrozenInstanceError):
        r.reason = "other"  # type: ignore[misc]
