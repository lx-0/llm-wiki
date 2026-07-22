"""C04 corpus-model seam: LintContext construction + footer-aware link graph.

The context is the single corpus read of a lint run: canonical enumeration
(includes `knowledge/MOCs/`), parsed frontmatter, stripped bodies, and a
footer-aware inbound map (the engine-written `## Backlinks` footers are NOT
link edges — backlog/orphan-check-footer-masking.md).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import lint


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _ctx(tmp_path: Path) -> lint.LintContext:
    return lint.build_context(
        vault=tmp_path, knowledge_dir=tmp_path / "knowledge", state={}
    )


# ── footer-aware orphan check (the live bug this candidate fixes) ────


def test_footer_link_does_not_rescue_orphan(tmp_path):
    """A links to B (body); M020 writes `[[A]]` into B's sentinel footer. The
    footer is engine-generated — it must NOT count as a B→A edge, otherwise
    every out-linking article gets a "free" inbound and the orphan check only
    catches fully isolated islands (the post-M020 silent regression)."""
    k = tmp_path / "knowledge"
    _write(k / "concepts" / "a.md", "Body link to [[b]].")
    _write(
        k / "concepts" / "b.md",
        "No outgoing body links.\n\n<!-- backlinks:begin -->\n\n## Backlinks\n\n"
        "- [[a]]\n\n<!-- backlinks:end -->\n",
    )
    flagged = {i.file for i in lint.check_orphan_pages(_ctx(tmp_path))}
    assert "concepts/a.md" in flagged  # only inbound is b's engine footer
    assert "concepts/b.md" not in flagged  # a's BODY link is a real edge


def test_body_link_still_counts_as_inbound(tmp_path):
    k = tmp_path / "knowledge"
    _write(k / "concepts" / "a.md", "See [[b]].")
    _write(k / "concepts" / "b.md", "See [[a]] right back.")
    flagged = {i.file for i in lint.check_orphan_pages(_ctx(tmp_path))}
    assert flagged == set()


def test_index_membership_still_rescues_orphan(tmp_path):
    """Decided with the footer fix: in-index.md membership keeps counting as
    non-orphan (unchanged from pre-C04 behaviour)."""
    k = tmp_path / "knowledge"
    _write(k / "concepts" / "lonely.md", "No links at all.")
    _write(k / "index.md", "| [[concepts/lonely]] | summary | src | 2026-05-01 |")
    flagged = {i.file for i in lint.check_orphan_pages(_ctx(tmp_path))}
    assert "concepts/lonely.md" not in flagged


def test_facts_and_mocs_are_orphan_exempt(tmp_path):
    """Facts are authoritative overrides; MOC hubs are graph roots (they link
    out; nothing links back to a hub) — neither is an orphan finding."""
    k = tmp_path / "knowledge"
    _write(k / "facts" / "hard-fact.md", "---\ntype: fact\n---\nNo inbound.")
    _write(k / "MOCs" / "concepts.md", "---\ntype: moc\n---\nHub: [[../concepts/x]]")
    _write(k / "concepts" / "x.md", "Linked from the MOC.")
    flagged = {i.file for i in lint.check_orphan_pages(_ctx(tmp_path))}
    assert "facts/hard-fact.md" not in flagged
    assert "MOCs/concepts.md" not in flagged
    # x has a real body inbound from the MOC hub
    assert "concepts/x.md" not in flagged


def test_self_link_is_not_inbound(tmp_path):
    k = tmp_path / "knowledge"
    _write(k / "concepts" / "selfy.md", "I link [[selfy]] to myself.")
    flagged = {i.file for i in lint.check_orphan_pages(_ctx(tmp_path))}
    assert "concepts/selfy.md" in flagged


# ── canonical enumeration includes MOCs ──────────────────────────────


def test_context_enumerates_mocs(tmp_path):
    k = tmp_path / "knowledge"
    _write(k / "MOCs" / "projects.md", "---\ntype: moc\n---\n# Hub")
    _write(k / "concepts" / "a.md", "body")
    ctx = _ctx(tmp_path)
    rels = {a.rel for a in ctx.articles}
    assert "MOCs/projects.md" in rels
    assert "concepts/a.md" in rels


def test_article_type_check_reaches_mocs(tmp_path):
    """FOLDER_TO_TYPE['MOCs'] was unreachable pre-C04 (the 8-flat-dir walker
    never enumerated MOCs/). A mistyped MOC page must now be flagged."""
    k = tmp_path / "knowledge"
    _write(k / "MOCs" / "wrong.md", "---\ntype: concept\n---\n# Not a moc")
    _write(k / "MOCs" / "right.md", "---\ntype: moc\n---\n# Proper hub")
    issues = lint.check_article_type(_ctx(tmp_path))
    by_file = {i.file: i.check for i in issues}
    assert by_file.get("MOCs/wrong.md") == "type_mismatch"
    assert "MOCs/right.md" not in by_file


# ── context internals ────────────────────────────────────────────────


def test_context_parses_frontmatter_and_strips_body(tmp_path):
    k = tmp_path / "knowledge"
    _write(k / "concepts" / "a.md", "---\ntype: concept\ntags: [x]\n---\n\nThe body.")
    ctx = _ctx(tmp_path)
    art = next(a for a in ctx.articles if a.rel == "concepts/a.md")
    assert art.fm == {"type": "concept", "tags": ["x"]}
    assert art.body.strip() == "The body."
    assert art.slug == "concepts/a"


def test_inbound_map_is_footer_aware_and_deduped(tmp_path):
    k = tmp_path / "knowledge"
    # a links b twice (counts once); c links b; b's footer names a (no edge).
    _write(k / "concepts" / "a.md", "[[b]] and again [[b]].")
    _write(
        k / "concepts" / "b.md",
        "Nothing.\n\n<!-- backlinks:begin -->\n\n## Backlinks\n\n- [[a]]\n\n<!-- backlinks:end -->\n",
    )
    _write(k / "concepts" / "c.md", "See [[b]].")
    ctx = _ctx(tmp_path)
    assert ctx.inbound.get("concepts/b") == {"concepts/a", "concepts/c"}
    assert "concepts/a" not in ctx.inbound  # footer link produced no edge


def test_unreadable_index_yields_empty_membership(tmp_path):
    k = tmp_path / "knowledge"
    _write(k / "concepts" / "a.md", "no links")
    ctx = _ctx(tmp_path)
    assert ctx.index_content == ""
