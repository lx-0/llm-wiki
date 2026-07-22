"""Behavioral coverage for the structural lint checks that had none (C04).

Before the LintContext seam these checks were zero-arg module-global functions,
testable only by monkeypatching `lint.KNOWLEDGE_DIR` & friends — so 9 of 19
never got tests. Now each runs over an in-memory corpus via
`lint.build_context(vault=..., knowledge_dir=..., state=...)`:

- check_broken_links
- check_orphan_sources
- check_stale_articles
- check_qa_schema
- check_daily_consistency
- check_sparse_articles
- check_compile_role
- check_author_required_on_source_and_final

(the ninth previously-uncovered check, `check_missing_backlinks`, was removed
in C04 — reciprocity is an M020 engine invariant, see DECISIONS.)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import lint
from core.utils import file_hash


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _ctx(tmp_path: Path, state: dict | None = None) -> lint.LintContext:
    return lint.build_context(
        vault=tmp_path, knowledge_dir=tmp_path / "knowledge", state=state or {}
    )


def _codes(issues: list[lint.Issue]) -> set[str]:
    return {i.check for i in issues}


# ── check_broken_links ───────────────────────────────────────────────


def test_broken_link_flagged_resolvable_link_passes(tmp_path):
    k = tmp_path / "knowledge"
    _write(k / "concepts" / "a.md", "Good [[b]] and bad [[does-not-exist]].")
    _write(k / "concepts" / "b.md", "Target exists.")
    issues = lint.check_broken_links(_ctx(tmp_path))
    assert len(issues) == 1
    iss = issues[0]
    assert iss.check == "broken_link"
    assert iss.severity == "error"
    assert iss.file == "concepts/a.md"
    assert iss.target_slug == "does-not-exist"  # structured payload, not prose


def test_broken_link_resolves_cross_folder_and_vault_relative(tmp_path):
    """The single resolver tries source-relative, vault root, and knowledge/ —
    all three historic link forms must pass."""
    k = tmp_path / "knowledge"
    _write(tmp_path / "daily" / "2026-01-05.md", "substrate file")
    _write(k / "people" / "alex.md", "A person.")
    _write(
        k / "concepts" / "a.md",
        "Cross [[../people/alex]] plus knowledge-absolute [[people/alex]] "
        "plus substrate [[../../daily/2026-01-05.md]].",
    )
    assert lint.check_broken_links(_ctx(tmp_path)) == []


def test_broken_link_in_backlinks_footer_is_still_flagged(tmp_path):
    """broken_link scans the FULL text (footer included) — a stale footer entry
    pointing at a deleted article is a real defect, unlike the edge semantics
    (orphans) where footers are excluded."""
    k = tmp_path / "knowledge"
    _write(
        k / "concepts" / "a.md",
        "Body.\n\n<!-- backlinks:begin -->\n\n## Backlinks\n\n"
        "- [[deleted-article]]\n\n<!-- backlinks:end -->\n",
    )
    issues = lint.check_broken_links(_ctx(tmp_path))
    assert _codes(issues) == {"broken_link"}


# ── check_orphan_sources ─────────────────────────────────────────────


def test_uningested_source_flagged_ingested_passes(tmp_path):
    (tmp_path / "knowledge").mkdir()
    _write(tmp_path / "raw" / "notes" / "new.md", "never compiled")
    _write(tmp_path / "daily" / "2026-01-05.md", "already compiled")
    state = {"ingested": {"daily/2026-01-05.md": "somehash"}}
    issues = lint.check_orphan_sources(_ctx(tmp_path, state=state))
    assert [i.file for i in issues] == ["raw/notes/new.md"]
    assert issues[0].check == "orphan_source"
    assert issues[0].severity == "warning"


def test_no_sources_no_orphan_source_issues(tmp_path):
    (tmp_path / "knowledge").mkdir()
    assert lint.check_orphan_sources(_ctx(tmp_path)) == []


# ── check_stale_articles ─────────────────────────────────────────────


def test_stale_when_source_hash_changed(tmp_path):
    (tmp_path / "knowledge").mkdir()
    src = tmp_path / "raw" / "notes" / "note.md"
    _write(src, "original content")
    state = {"ingested": {"raw/notes/note.md": file_hash(src)}}
    # Unchanged → not stale.
    assert lint.check_stale_articles(_ctx(tmp_path, state=state)) == []
    # Source edited after compile → stale.
    src.write_text("edited content", encoding="utf-8")
    issues = lint.check_stale_articles(_ctx(tmp_path, state=state))
    assert [i.file for i in issues] == ["raw/notes/note.md"]
    assert issues[0].check == "stale_article"


def test_stale_handles_legacy_dict_state_shape(tmp_path):
    """Older state files stored {hash: ..., compiled_at: ...} dicts instead of
    the bare hash string — both shapes must be compared correctly."""
    (tmp_path / "knowledge").mkdir()
    src = tmp_path / "raw" / "notes" / "legacy.md"
    _write(src, "content")
    fresh = {"ingested": {"raw/notes/legacy.md": {"hash": file_hash(src)}}}
    assert lint.check_stale_articles(_ctx(tmp_path, state=fresh)) == []
    stale = {"ingested": {"raw/notes/legacy.md": {"hash": "different"}}}
    assert _codes(lint.check_stale_articles(_ctx(tmp_path, state=stale))) == {
        "stale_article"
    }


def test_uningested_source_is_not_stale(tmp_path):
    """Never-compiled sources belong to check_orphan_sources, not stale."""
    (tmp_path / "knowledge").mkdir()
    _write(tmp_path / "raw" / "notes" / "new.md", "content")
    assert lint.check_stale_articles(_ctx(tmp_path)) == []


# ── check_qa_schema ──────────────────────────────────────────────────


def test_qa_schema_passes_canonical_note(tmp_path, monkeypatch):
    monkeypatch.setattr(lint, "_domain_tags", lambda: ("fleet", "llm-wiki"))
    k = tmp_path / "knowledge"
    _write(k / "qa" / "how-x.md", "---\ntype: qa\ntags: [fleet]\n---\nAnswer.")
    _write(k / "index.md", "| [[qa/how-x]] | q | src | 2026-01-05 |")
    assert lint.check_qa_schema(_ctx(tmp_path)) == []


def test_qa_schema_flags_all_three_rules(tmp_path, monkeypatch):
    """Wrong type + not in index + no domain tag — each rule fires its own
    issue code so the drift is independently routable."""
    monkeypatch.setattr(lint, "_domain_tags", lambda: ("fleet", "llm-wiki"))
    k = tmp_path / "knowledge"
    _write(k / "qa" / "drifted.md", "---\ntype: concept\ntags: [misc]\n---\nBody.")
    issues = lint.check_qa_schema(_ctx(tmp_path))
    assert _codes(issues) == {"qa_missing_type", "qa_not_in_index", "qa_no_domain_tag"}
    by_code = {i.check: i for i in issues}
    assert by_code["qa_missing_type"].severity == "error"
    assert by_code["qa_not_in_index"].severity == "warning"


# ── check_daily_consistency ──────────────────────────────────────────


def test_daily_subfolder_without_digest_flagged(tmp_path):
    (tmp_path / "knowledge").mkdir()
    _write(tmp_path / "daily" / "2026-01-05" / "sessions.md", "capture")
    issues = lint.check_daily_consistency(_ctx(tmp_path))
    assert _codes(issues) == {"daily_missing_digest"}
    assert issues[0].file == "daily/2026-01-05.md"


def test_daily_paired_digest_passes(tmp_path):
    (tmp_path / "knowledge").mkdir()
    _write(tmp_path / "daily" / "2026-01-05" / "sessions.md", "capture")
    _write(
        tmp_path / "daily" / "2026-01-05.md",
        "---\ntype: daily-digest\n---\nDigest body.",
    )
    assert lint.check_daily_consistency(_ctx(tmp_path)) == []


def test_daily_root_without_digest_type_flagged(tmp_path):
    """Root file next to a subfolder that is NOT a real digest (legacy
    flat-daily preserved by the migration) gets its own code."""
    (tmp_path / "knowledge").mkdir()
    _write(tmp_path / "daily" / "2026-01-05" / "sessions.md", "capture")
    _write(tmp_path / "daily" / "2026-01-05.md", "no frontmatter at all")
    assert _codes(lint.check_daily_consistency(_ctx(tmp_path))) == {
        "daily_root_not_digest"
    }


def test_daily_unknown_source_and_legacy_flat_flagged(tmp_path):
    (tmp_path / "knowledge").mkdir()
    _write(tmp_path / "daily" / "2026-01-05" / "sessions.md", "known source")
    _write(tmp_path / "daily" / "2026-01-05" / "scratchpad.md", "stray file")
    _write(
        tmp_path / "daily" / "2026-01-05.md",
        "---\ntype: daily-digest\n---\nDigest.",
    )
    _write(tmp_path / "daily" / "2026-01-04.md", "flat pre-rollup daily")
    issues = lint.check_daily_consistency(_ctx(tmp_path))
    by_code = {i.check: i.file for i in issues}
    assert by_code == {
        "daily_unknown_source": "daily/2026-01-05/scratchpad.md",
        "daily_legacy_flat": "daily/2026-01-04.md",
    }


def test_daily_today_is_skipped(tmp_path):
    """The digest for the current day legitimately hasn't run yet."""
    from datetime import date

    (tmp_path / "knowledge").mkdir()
    today = date.today().isoformat()
    _write(tmp_path / "daily" / today / "sessions.md", "capture")
    assert lint.check_daily_consistency(_ctx(tmp_path)) == []


# ── check_sparse_articles ────────────────────────────────────────────


def test_sparse_article_flagged_substantive_passes(tmp_path):
    k = tmp_path / "knowledge"
    long_body = "word " * (lint.SPARSE_THRESHOLD + 10)
    _write(k / "concepts" / "thin.md", "---\ntype: concept\n---\ntoo short")
    _write(k / "concepts" / "full.md", f"---\ntype: concept\n---\n{long_body}")
    issues = lint.check_sparse_articles(_ctx(tmp_path))
    assert [i.file for i in issues] == ["concepts/thin.md"]
    assert issues[0].severity == "suggestion"
    assert issues[0].check == "sparse_article"


def test_sparse_word_count_excludes_frontmatter(tmp_path):
    """A file whose frontmatter pads it over the threshold is still sparse —
    only the body counts."""
    k = tmp_path / "knowledge"
    fat_fm = "\n".join(f"key{i}: value{i}" for i in range(lint.SPARSE_THRESHOLD))
    _write(k / "concepts" / "fm-heavy.md", f"---\n{fat_fm}\n---\nshort body")
    assert _codes(lint.check_sparse_articles(_ctx(tmp_path))) == {"sparse_article"}


def test_sparse_exempts_facts(tmp_path):
    k = tmp_path / "knowledge"
    _write(k / "facts" / "terse.md", "---\ntype: fact\n---\nX is false.")
    assert lint.check_sparse_articles(_ctx(tmp_path)) == []


# ── check_compile_role ───────────────────────────────────────────────


def test_compile_role_invalid_value_flagged_everywhere(tmp_path):
    """The walk covers raw/, daily/, inbox/ AND the knowledge corpus."""
    k = tmp_path / "knowledge"
    _write(tmp_path / "raw" / "notes" / "bad.md", "---\ncompile_role: bogus\n---\n")
    _write(tmp_path / "inbox" / "drop.md", "---\ncompile_role: final\n---\n")
    _write(k / "concepts" / "ok.md", "---\ncompile_role: source-and-final\nauthor: alex\n---\nBody.")
    issues = lint.check_compile_role(_ctx(tmp_path))
    assert {i.file for i in issues} == {"raw/notes/bad.md", "inbox/drop.md"}
    assert _codes(issues) == {"compile_role_invalid"}
    assert all(i.severity == "error" for i in issues)


def test_compile_role_absent_is_fine(tmp_path):
    """Files without compile_role: use location-based inference — no issue."""
    (tmp_path / "knowledge").mkdir()
    _write(tmp_path / "raw" / "notes" / "plain.md", "no frontmatter")
    _write(tmp_path / "daily" / "2026-01-05.md", "---\ntype: daily-digest\n---\n")
    assert lint.check_compile_role(_ctx(tmp_path)) == []


# ── check_author_required_on_source_and_final ────────────────────────


def test_source_and_final_without_author_flagged(tmp_path):
    k = tmp_path / "knowledge"
    _write(
        k / "concepts" / "personal-essay.md",
        "---\ncompile_role: source-and-final\n---\nMy own words.",
    )
    issues = lint.check_author_required_on_source_and_final(_ctx(tmp_path))
    assert [i.file for i in issues] == ["knowledge/concepts/personal-essay.md"]
    assert issues[0].check == "source_and_final_missing_author"
    assert issues[0].severity == "error"


def test_source_and_final_with_author_passes(tmp_path):
    k = tmp_path / "knowledge"
    _write(
        k / "concepts" / "personal-essay.md",
        "---\ncompile_role: source-and-final\nauthor: alex\n---\nMy own words.",
    )
    _write(
        tmp_path / "raw" / "notes" / "plain-source.md",
        "---\ncompile_role: source-only\n---\nNo author needed here.",
    )
    assert lint.check_author_required_on_source_and_final(_ctx(tmp_path)) == []
