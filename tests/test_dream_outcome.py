"""Typed DreamOutcome + single exit-code map + pure pre/post-SDK helpers.

These exercise the parts extracted from dream_entity's async monolith as pure
functions — no SDK mock, no module-global monkeypatch. The exit-code tests pin
the monitoring-blindspot fix: per_call_timeout AND prompt_too_large MUST map to
a nonzero CLI exit so an unattended piggyback records `failed:<rc>` (they both
exited 0 before, so piggyback_runner recorded a false `ok`).
"""

from __future__ import annotations

import logging
from pathlib import Path

import dream
from dream import (
    CorpusBreakdown,
    DreamOutcome,
    EntityRef,
    classify_dream_kind,
    classify_post_sdk_write,
    dream_exit_code,
    pre_sdk_skip,
)


def _outcome(kind: str | None) -> DreamOutcome:
    ent = EntityRef(slug="x", kind="people", page=Path("x.md"), type_value="person")
    return DreamOutcome(
        entity=ent, corpus_count=0, corpus_chars=0, actual_cost_usd=0.0,
        input_tokens=0, output_tokens=0, sdk_result_text="", kind=kind,
    )


# ── status classification ────────────────────────────────────────────


def test_classify_dream_kind_status() -> None:
    assert classify_dream_kind(None) == "synthesized"
    assert classify_dream_kind("no_substrate") == "skipped"
    assert classify_dream_kind("no_entity_substrate") == "skipped"
    assert classify_dream_kind("dry_run") == "skipped"
    assert classify_dream_kind("prompt_too_large") == "failed"
    assert classify_dream_kind("per_call_timeout") == "failed"
    assert classify_dream_kind("sdk_failure") == "failed"


def test_outcome_status_and_failed_properties() -> None:
    assert _outcome(None).status == "synthesized"
    assert _outcome(None).failed is False
    assert _outcome("dry_run").status == "skipped"
    assert _outcome("dry_run").failed is False
    assert _outcome("per_call_timeout").status == "failed"
    assert _outcome("per_call_timeout").failed is True


# ── exit-code map (single source of truth) ───────────────────────────


def test_skip_kinds_and_success_exit_zero() -> None:
    for kind in (None, "no_substrate", "no_entity_substrate", "dry_run"):
        assert _outcome(kind).exit_code == 0, kind
        assert dream_exit_code(_outcome(kind)) == 0, kind


def test_failure_kinds_exit_nonzero() -> None:
    # The monitoring-blindspot fix: per_call_timeout + prompt_too_large were
    # exit 0 everywhere before, so a hung-then-aborted unattended dream recorded
    # a false `ok` in piggyback-state.json. They must be nonzero now.
    assert _outcome("prompt_too_large").exit_code == 3
    assert _outcome("sdk_failure").exit_code == 4
    assert _outcome("per_call_timeout").exit_code == 6
    for kind in ("prompt_too_large", "sdk_failure", "per_call_timeout"):
        assert dream_exit_code(_outcome(kind)) != 0, kind


def test_dream_exit_code_batch_takes_highest() -> None:
    # A sweep result list returns the highest-severity nonzero code, and a clean
    # batch returns 0.
    assert dream_exit_code([_outcome(None), _outcome("dry_run")]) == 0
    assert dream_exit_code([_outcome(None), _outcome("per_call_timeout")]) == 6
    assert dream_exit_code(
        [_outcome("prompt_too_large"), _outcome("per_call_timeout")]
    ) == 6
    assert dream_exit_code([]) == 0


def test_exit_code_kinds_partition_cleanly() -> None:
    """Every kind is either a skip (exit 0) or a failure (nonzero) — no kind is
    both, and the failure kinds are exactly the ones in the exit-code map."""
    assert dream._DREAM_SKIP_KINDS.isdisjoint(dream._DREAM_FAILURE_KINDS)
    assert set(dream._DREAM_EXIT_CODES) == set(dream._DREAM_FAILURE_KINDS)


# ── pre-SDK gate (pure) ──────────────────────────────────────────────


def _breakdown(*, authored=(), recent=(), digests=(), sampled=()) -> CorpusBreakdown:
    return CorpusBreakdown(
        tier1_entity_page=None,
        tier1_authored=list(authored),
        tier1_recent=list(recent),
        tier1_digests=list(digests),
        tier2_sampled=list(sampled),
        tier2_pool_size=0,
    )


def test_pre_sdk_skip_no_substrate_when_corpus_empty() -> None:
    assert pre_sdk_skip(_breakdown(), require_entity_substrate=True) == "no_substrate"
    assert pre_sdk_skip(_breakdown(), require_entity_substrate=False) == "no_substrate"


def test_pre_sdk_skip_no_entity_substrate_when_only_digests() -> None:
    bd = _breakdown(digests=[Path("daily/2026-05-10.md")])
    assert pre_sdk_skip(bd, require_entity_substrate=True) == "no_entity_substrate"
    # With the guard off, a digests-only corpus is allowed through.
    assert pre_sdk_skip(bd, require_entity_substrate=False) is None


def test_pre_sdk_skip_proceeds_with_entity_substrate() -> None:
    bd = _breakdown(recent=[Path("raw/notes/n.md")], digests=[Path("daily/x.md")])
    assert pre_sdk_skip(bd, require_entity_substrate=True) is None
    bd2 = _breakdown(authored=[Path("knowledge/concepts/a.md")])
    assert pre_sdk_skip(bd2, require_entity_substrate=True) is None
    bd3 = _breakdown(sampled=[Path("raw/notes/old.md")])
    assert pre_sdk_skip(bd3, require_entity_substrate=True) is None


# ── post-SDK write classifier (pure) ─────────────────────────────────


def test_classify_post_sdk_changed_page_is_success() -> None:
    v = classify_post_sdk_write(
        pre_mtime=1.0, pre_size=100, post_mtime=2.0, post_size=120,
        result_text="whatever",
    )
    assert v.page_changed is True
    assert v.insufficient_corpus is False
    assert v.level == logging.INFO


def test_classify_post_sdk_insufficient_corpus_is_info_noop() -> None:
    v = classify_post_sdk_write(
        pre_mtime=5.0, pre_size=100, post_mtime=5.0, post_size=100,
        result_text="INSUFFICIENT_CORPUS: 0 claims from 8 sources",
    )
    assert v.page_changed is False
    assert v.insufficient_corpus is True
    assert v.level == logging.INFO


def test_classify_post_sdk_silent_noop_is_warning() -> None:
    v = classify_post_sdk_write(
        pre_mtime=5.0, pre_size=100, post_mtime=5.0, post_size=100,
        result_text="I would update the State section but ...",
    )
    assert v.page_changed is False
    assert v.insufficient_corpus is False
    assert v.level == logging.WARNING
