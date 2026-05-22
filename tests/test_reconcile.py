"""Deterministic logic of the concept-reconciliation routine.

The LLM rewrite itself is not unit-tested (non-deterministic, see
`feedback_llm_output_non_deterministic`). These cover the orchestration:
signal grouping, concepts-only scope, cooldown, and the dry-run / cost-cap
short-circuits that gate the SDK call.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


def test_fact_violations_by_slug_groups_filters_and_absolutizes(monkeypatch, tmp_path):
    import reconcile

    monkeypatch.setattr(reconcile, "ROOT_DIR", tmp_path)
    # Canned lint output: two concept hits for one fact, one for another,
    # plus a NON-concept hit (people/) that must be filtered out, plus a
    # duplicate that must be deduped.
    issues = [
        {"file": "concepts/foo.md", "detail": "negation term from hard fact `facts/no-x`"},
        {"file": "concepts/bar.md", "detail": "negation term from hard fact `facts/no-x`"},
        {"file": "concepts/foo.md", "detail": "another term from hard fact `facts/no-x`"},  # dup file
        {"file": "concepts/baz.md", "detail": "term from hard fact `facts/no-y`"},
        {"file": "people/alex.md", "detail": "term from hard fact `facts/no-x`"},  # not a concept
        {"file": "concepts/qux.md", "detail": "no slug here"},  # no fact slug → skipped
    ]
    monkeypatch.setattr(reconcile.lint, "check_facts_violations", lambda: issues)

    out = reconcile._fact_violations_by_slug()

    assert set(out.keys()) == {"no-x", "no-y"}
    assert out["no-x"] == [
        str((tmp_path / "knowledge/concepts/foo.md").resolve()),
        str((tmp_path / "knowledge/concepts/bar.md").resolve()),
    ]  # deduped, absolute, concepts-only, order preserved
    assert out["no-y"] == [str((tmp_path / "knowledge/concepts/baz.md").resolve())]


def test_within_cooldown(monkeypatch, tmp_path):
    import reconcile

    facts = tmp_path / "facts"
    facts.mkdir()
    monkeypatch.setattr(reconcile, "FACTS_DIR", facts)

    fresh = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    stale = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    (facts / "fresh.md").write_text(f"---\ntype: fact\nlast_reconciled: '{fresh}'\n---\n\nx\n")
    (facts / "stale.md").write_text(f"---\ntype: fact\nlast_reconciled: '{stale}'\n---\n\nx\n")
    (facts / "never.md").write_text("---\ntype: fact\n---\n\nx\n")

    assert reconcile._within_cooldown("fresh", cooldown_days=14) is True
    assert reconcile._within_cooldown("stale", cooldown_days=14) is False
    assert reconcile._within_cooldown("never", cooldown_days=14) is False  # no stamp
    assert reconcile._within_cooldown("absent", cooldown_days=14) is False  # no file


def test_reconcile_fact_dry_run_makes_no_sdk_call(monkeypatch, tmp_path):
    from facts import correct_apply

    facts = tmp_path / "facts"
    facts.mkdir()
    monkeypatch.setattr(correct_apply, "FACTS_DIR", facts)
    monkeypatch.setattr(correct_apply, "ROOT_DIR", tmp_path)
    (facts / "no-x.md").write_text("---\ntype: fact\nstatus: negation\nnegation_terms: [x]\n---\n\nX is false.\n")

    def boom(*a, **kw):
        raise AssertionError("query() must not be called in dry-run")

    monkeypatch.setattr(correct_apply, "query", boom)

    res = asyncio.run(correct_apply.reconcile_fact(
        "no-x", [str(tmp_path / "knowledge/concepts/foo.md")],
        dry_run=True, per_fact_cap_usd=1.0,
    ))
    assert res.status == "dry_run"
    assert res.cost_usd == 0.0


def test_reconcile_fact_cost_cap_skips(monkeypatch, tmp_path):
    from facts import correct_apply

    facts = tmp_path / "facts"
    facts.mkdir()
    monkeypatch.setattr(correct_apply, "FACTS_DIR", facts)
    monkeypatch.setattr(correct_apply, "ROOT_DIR", tmp_path)
    (facts / "no-x.md").write_text("---\ntype: fact\nstatus: negation\nnegation_terms: [x]\n---\n\nX is false.\n")

    def boom(*a, **kw):
        raise AssertionError("query() must not be called when over cost cap")

    monkeypatch.setattr(correct_apply, "query", boom)

    res = asyncio.run(correct_apply.reconcile_fact(
        "no-x", [str(tmp_path / "knowledge/concepts/foo.md")],
        dry_run=False, per_fact_cap_usd=0.0,  # impossible cap → must skip pre-flight
    ))
    assert res.status == "skipped"
    assert "cap" in res.detail.lower()


def test_reconcile_fact_missing_fact_fails(monkeypatch, tmp_path):
    from facts import correct_apply

    facts = tmp_path / "facts"
    facts.mkdir()
    monkeypatch.setattr(correct_apply, "FACTS_DIR", facts)
    res = asyncio.run(correct_apply.reconcile_fact(
        "ghost", ["/x/concepts/foo.md"], dry_run=True, per_fact_cap_usd=1.0,
    ))
    assert res.status == "failed"
