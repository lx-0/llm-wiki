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
    import lint
    import reconcile

    monkeypatch.setattr(reconcile, "ROOT_DIR", tmp_path)
    # Canned lint output: two concept hits for one fact, one for another,
    # plus a NON-concept hit (people/) that must be filtered out, plus a
    # duplicate that must be deduped. Grouping keys on the structured
    # `fact_slug` payload — never on the prose detail (C04).
    def iss(file, slug):
        return lint.issue("warning", "fact_violation", file, "detail prose", fact_slug=slug)

    issues = [
        iss("concepts/foo.md", "no-x"),
        iss("concepts/bar.md", "no-x"),
        iss("concepts/foo.md", "no-x"),  # dup file
        iss("concepts/baz.md", "no-y"),
        iss("people/alex.md", "no-x"),  # not a concept
        iss("concepts/qux.md", None),  # no fact slug → skipped
    ]
    monkeypatch.setattr(reconcile.lint, "build_context", lambda **kw: None)
    monkeypatch.setattr(reconcile.lint, "check_facts_violations", lambda ctx: issues)

    out = reconcile._fact_violations_by_slug()

    assert set(out.keys()) == {"no-x", "no-y"}
    assert out["no-x"] == [
        str((tmp_path / "knowledge/concepts/foo.md").resolve()),
        str((tmp_path / "knowledge/concepts/bar.md").resolve()),
    ]  # deduped, absolute, concepts-only, order preserved
    assert out["no-y"] == [str((tmp_path / "knowledge/concepts/baz.md").resolve())]


def test_fact_violations_slug_handles_non_ascii(monkeypatch, tmp_path):
    """Fact slugs with non-ASCII (umlauts, incl. NFD-decomposed) must survive
    grouping. Regression: `sidney-wach-ist-männlich` with NFD `ä` (a + U+0308)
    once truncated to `sidney-wach-ist-ma` under a prose-scraping ASCII regex →
    "no such fact". The structured `fact_slug` payload passes through verbatim."""
    import unicodedata

    import lint
    import reconcile

    monkeypatch.setattr(reconcile, "ROOT_DIR", tmp_path)
    nfd = unicodedata.normalize("NFD", "sidney-wach-ist-männlich")  # ä → a + U+0308
    issues = [lint.issue(
        "warning", "fact_violation", "concepts/sidney.md",
        "Article contains negation term 'weiblich'…", fact_slug=nfd,
    )]
    monkeypatch.setattr(reconcile.lint, "build_context", lambda **kw: None)
    monkeypatch.setattr(reconcile.lint, "check_facts_violations", lambda ctx: issues)
    out = reconcile._fact_violations_by_slug()
    assert list(out.keys()) == [nfd]  # full slug survives, not truncated at the umlaut


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
        dry_run=True,
    ))
    assert res.status == "dry_run"
    assert res.cost_usd == 0.0


def test_run_skips_facts_exceeding_max_files(monkeypatch):
    """Structural gate (replaces the old USD pre-flight): a fact violating more
    than max_files_per_fact concept files is skipped for manual review and
    reconcile_fact is never called for it."""
    import reconcile

    monkeypatch.setattr(reconcile, "_fact_violations_by_slug",
                        lambda: {"broad": [f"/c/{i}.md" for i in range(50)],
                                 "narrow": ["/c/a.md"]})
    monkeypatch.setattr(reconcile.CONFIG.limits, "concept_reconcile_max_files_per_fact", 25)
    monkeypatch.setattr(reconcile.CONFIG.limits, "concept_reconcile_max_facts_per_run", 10)
    monkeypatch.setattr(reconcile, "_within_cooldown", lambda *a, **k: False)

    called: list[str] = []

    async def fake_reconcile_fact(slug, files, *, dry_run):
        from facts.correct_apply import ReconcileResult
        called.append(slug)
        return ReconcileResult(slug, "dry_run", files=files)

    monkeypatch.setattr(reconcile, "reconcile_fact", fake_reconcile_fact)
    asyncio.run(reconcile.run(apply=False, limit=None))
    assert called == ["narrow"]  # broad (50 files > 25) skipped


def test_run_respects_max_facts_per_run(monkeypatch):
    import reconcile

    monkeypatch.setattr(reconcile, "_fact_violations_by_slug",
                        lambda: {f"f{i}": ["/c/a.md"] for i in range(5)})
    monkeypatch.setattr(reconcile.CONFIG.limits, "concept_reconcile_max_files_per_fact", 25)
    monkeypatch.setattr(reconcile.CONFIG.limits, "concept_reconcile_max_facts_per_run", 2)
    monkeypatch.setattr(reconcile, "_within_cooldown", lambda *a, **k: False)

    called: list[str] = []

    async def fake_reconcile_fact(slug, files, *, dry_run):
        from facts.correct_apply import ReconcileResult
        called.append(slug)
        return ReconcileResult(slug, "dry_run", files=files)

    monkeypatch.setattr(reconcile, "reconcile_fact", fake_reconcile_fact)
    asyncio.run(reconcile.run(apply=False, limit=None))
    assert len(called) == 2  # capped at max_facts_per_run


def test_reconcile_fact_missing_fact_fails(monkeypatch, tmp_path):
    from facts import correct_apply

    facts = tmp_path / "facts"
    facts.mkdir()
    monkeypatch.setattr(correct_apply, "FACTS_DIR", facts)
    res = asyncio.run(correct_apply.reconcile_fact(
        "ghost", ["/x/concepts/foo.md"], dry_run=True,
    ))
    assert res.status == "failed"
