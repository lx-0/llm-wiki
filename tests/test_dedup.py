"""Tests for `dedup` — entity-deduplication detection + merge (issue #3).

Covers the German-aware phonetic key, the three detection signals (phonetic
collision, phonetic-near / fuzzy title, shared source), cross-kind isolation,
the markdown section merge (Timeline/Action Items/Open Threads fold + dedup),
the end-to-end merge (frontmatter union, B backed-up + deleted, wikilink
rewrite B→A, hard fact), and dry-run writing nothing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dedup import (
    CandidatePair,
    find_candidates,
    load_entities,
    merge_bodies,
    merge_pages,
    normalize,
    phonetic_key,
    rewrite_links,
)


# ── phonetic key + normalization ─────────────────────────────────────


def test_normalize_collapses_separators_and_accents():
    assert normalize("Josefine-Bartsch") == normalize("Josefine Bartsch") == "josefinebartsch"
    assert normalize("Müller") == "muller"
    assert normalize("Vëltari!") == "veltari"


@pytest.mark.parametrize(
    "a,b",
    [
        ("Veltari", "Veltary"),        # vowel-drop collision
        ("Mueller", "Müller"),        # ß/umlaut + spelling
        ("Sebastian", "Sebbastian"),  # doubled consonant
    ],
)
def test_phonetic_key_collides_for_variants(a, b):
    assert phonetic_key(a) == phonetic_key(b)


def test_phonetic_key_distinguishes_unrelated():
    assert phonetic_key("Yesterday") != phonetic_key("Fleet")
    assert phonetic_key("Anna") != phonetic_key("Hannah")


# ── detection ────────────────────────────────────────────────────────


def _vault(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, content in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    (tmp_path / ".obsidian").mkdir(exist_ok=True)
    return tmp_path


def _page(title: str, *, compiled_from: list[str] | None = None, body: str = "") -> str:
    fm = [f"title: {title}", "type: person"]
    if compiled_from:
        fm.append("compiled_from:")
        fm.extend(f"  - {s}" for s in compiled_from)
    return "---\n" + "\n".join(fm) + "\n---\n\n# " + title + "\n\n" + body


def test_detects_phonetic_collision(tmp_path: Path):
    v = _vault(tmp_path, {
        "knowledge/projects/veltari.md": _page("Veltari"),
        "knowledge/projects/veltary.md": _page("Veltary"),
    })
    cands = find_candidates(load_entities(v / "knowledge"), threshold=0.85)
    assert len(cands) == 1
    assert cands[0].key == frozenset({"veltari", "veltary"})
    assert any("phonetic" in r for r in cands[0].reasons)


def test_detects_headline_josefine_pair_below_raw_fuzzy(tmp_path: Path):
    """The headline example: raw fuzzy 0.78 < 0.85, but phonetic-near catches it."""
    v = _vault(tmp_path, {
        "knowledge/people/josefine-bartsch.md": _page("Josefine Bartsch"),
        "knowledge/people/josephine-bartc.md": _page("Josephine Bartc"),
    })
    cands = find_candidates(load_entities(v / "knowledge"), threshold=0.85)
    assert len(cands) == 1
    assert cands[0].key == frozenset({"josefine-bartsch", "josephine-bartc"})


def test_short_name_no_false_positive(tmp_path: Path):
    """Tim/Tom collapse to `tm` — too short to trust on fuzzy; not proposed."""
    v = _vault(tmp_path, {
        "knowledge/people/tim.md": _page("Tim"),
        "knowledge/people/tom.md": _page("Tom"),
    })
    cands = find_candidates(load_entities(v / "knowledge"), threshold=0.85)
    assert cands == []


def test_never_proposes_cross_kind(tmp_path: Path):
    v = _vault(tmp_path, {
        "knowledge/people/veltari.md": _page("Veltari"),
        "knowledge/projects/veltary.md": _page("Veltary"),
    })
    cands = find_candidates(load_entities(v / "knowledge"), threshold=0.85)
    assert cands == []


def test_shared_source_does_not_create_candidate(tmp_path: Path):
    """Two *different* entities sharing one daily-digest source is co-occurrence,
    not duplication — shared source alone must not propose a pair."""
    src = "daily/sessions/2025-11-14.md"
    v = _vault(tmp_path, {
        "knowledge/people/anna.md": _page("Anna", compiled_from=[src]),
        "knowledge/people/bettina.md": _page("Bettina", compiled_from=[src]),
    })
    cands = find_candidates(load_entities(v / "knowledge"), threshold=0.85)
    assert cands == []


def test_shared_source_boosts_name_match(tmp_path: Path):
    """A name match that ALSO shares a source gets boosted + annotated."""
    src = "raw/transcripts/jamie/2025-11-14--call.md"
    v = _vault(tmp_path, {
        "knowledge/people/veltari.md": _page("Veltari", compiled_from=[src]),
        "knowledge/people/veltary.md": _page("Veltary", compiled_from=[src]),
    })
    cands = find_candidates(load_entities(v / "knowledge"), threshold=0.85)
    assert len(cands) == 1
    assert "shared source" in cands[0].reasons
    assert cands[0].confidence > 0.9  # phonetic 0.9 + 0.05 boost


# ── section merge ────────────────────────────────────────────────────


def test_merge_bodies_folds_and_dedups():
    a = "## State\nAlpha state.\n\n## Timeline\n- 2025-01-01 met\n"
    b = "## State\nBeta state.\n\n## Timeline\n- 2025-01-01 met\n- 2025-02-02 lunch\n\n## Action Items\n- [ ] call back\n"
    out = merge_bodies(a, b)
    assert out.count("- 2025-01-01 met") == 1          # dedup by content
    assert "- 2025-02-02 lunch" in out                 # B-only timeline entry folded
    assert "## Action Items" in out and "call back" in out  # B-only section appended
    assert "Beta state." not in out                    # State is A's; not merged


# ── end-to-end merge ─────────────────────────────────────────────────


def test_merge_pages_endtoend(tmp_path: Path, monkeypatch):
    v = _vault(tmp_path, {
        "knowledge/people/josefine-bartsch.md": _page(
            "Josefine Bartsch", compiled_from=["raw/a.md"],
            body="## Timeline\n- 2025-01-01 met\n",
        ),
        "knowledge/people/josephine-bartc.md": _page(
            "Josephine Bartc", compiled_from=["raw/b.md"],
            body="## Timeline\n- 2025-02-02 lunch\n\n## Open Threads\n- pricing\n",
        ),
        # A third article linking to B — must be rewritten to A.
        "knowledge/projects/deal.md": "---\ntype: project\n---\n\n# Deal\n\nWith [[../people/josephine-bartc]].\n",
    })
    # Point FACTS_DIR at this vault so record_canonical_fact writes here.
    import core.paths as paths
    monkeypatch.setattr(paths, "FACTS_DIR", v / "knowledge" / "facts", raising=False)
    import facts.correct as correct
    monkeypatch.setattr(correct, "FACTS_DIR", v / "knowledge" / "facts", raising=False)

    ents = {e.slug: e for e in load_entities(v / "knowledge")}
    res = merge_pages(
        ents["josefine-bartsch"], ents["josephine-bartc"],
        canonical_name="Josefine Bartsch",
        knowledge_dir=v / "knowledge", vault=v, dry_run=False,
    )

    # B deleted + backed up.
    assert not (v / "knowledge/people/josephine-bartc.md").exists()
    assert res.backup is not None and res.backup.exists()

    kept = (v / "knowledge/people/josefine-bartsch.md").read_text()
    assert "- 2025-02-02 lunch" in kept           # B timeline folded in
    assert "## Open Threads" in kept              # B-only section appended
    assert "raw/b.md" in kept and "raw/a.md" in kept  # compiled_from union
    assert "Josephine Bartc" in kept                  # B title kept as alias

    # Wikilink in deal.md rewritten B→A.
    deal = (v / "knowledge/projects/deal.md").read_text()
    assert "josephine-bartc" not in deal
    assert "josefine-bartsch" in deal
    assert res.links_rewritten

    # Canonical-name hard fact recorded.
    assert res.fact is not None and res.fact.exists()
    fact_text = res.fact.read_text()
    assert "negation" in fact_text and "Josephine Bartc" in fact_text


def test_merge_pages_dry_run_writes_nothing(tmp_path: Path):
    v = _vault(tmp_path, {
        "knowledge/people/a.md": _page("Annaa", body="## Timeline\n- x\n"),
        "knowledge/people/b.md": _page("Annah", body="## Timeline\n- y\n"),
        "knowledge/projects/c.md": "---\ntype: project\n---\n\n# C\n\n[[../people/b]]\n",
    })
    ents = {e.slug: e for e in load_entities(v / "knowledge")}
    before = {p: p.read_text() for p in (v / "knowledge").rglob("*.md")}
    res = merge_pages(
        ents["a"], ents["b"], canonical_name="Annaa",
        knowledge_dir=v / "knowledge", vault=v, dry_run=True,
    )
    assert res.dry_run and res.backup is None and res.fact is None
    # Nothing on disk changed; B still present.
    assert (v / "knowledge/people/b.md").exists()
    after = {p: p.read_text() for p in (v / "knowledge").rglob("*.md")}
    assert before == after


def test_main_suggest_only(tmp_path: Path, monkeypatch, capsys):
    """The read path hooks/agents use: detect + print, exit 0, no writes."""
    v = _vault(tmp_path, {
        "knowledge/projects/veltari.md": _page("Veltari"),
        "knowledge/projects/veltary.md": _page("Veltary"),
    })
    import core.paths as paths
    monkeypatch.setattr(paths, "KNOWLEDGE_DIR", v / "knowledge", raising=False)
    monkeypatch.setattr(paths, "ROOT_DIR", v, raising=False)
    from dedup import main

    rc = main(["--suggest-only"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "veltari" in out and "veltary" in out
    assert (v / "knowledge/projects/veltary.md").exists()  # nothing merged


def test_main_merge_subcommand_dry_run(tmp_path: Path, monkeypatch, capsys):
    v = _vault(tmp_path, {
        "knowledge/people/keep.md": _page("Keep"),
        "knowledge/people/drop.md": _page("Drop"),
    })
    import core.paths as paths
    monkeypatch.setattr(paths, "KNOWLEDGE_DIR", v / "knowledge", raising=False)
    monkeypatch.setattr(paths, "ROOT_DIR", v, raising=False)
    import dedup
    monkeypatch.setattr(dedup, "_ask", lambda *_: "y")  # auto-confirm

    rc = dedup.main(["--dry-run", "merge", "drop", "--into", "keep"])
    assert rc == 0
    assert (v / "knowledge/people/drop.md").exists()  # dry-run wrote nothing


def test_rewrite_links_relative_and_idempotent(tmp_path: Path):
    v = _vault(tmp_path, {
        "knowledge/people/keep.md": "---\ntype: person\n---\n\n# Keep\n",
        "knowledge/people/drop.md": "---\ntype: person\n---\n\n# Drop\n",
        "knowledge/projects/x.md": "---\ntype: project\n---\n\n# X\n\nsee [[../people/drop]] and [[../people/drop|Drop]]\n",
    })
    changed = rewrite_links(
        v / "knowledge", v, v / "knowledge/people/drop.md", "people/keep", dry_run=False,
    )
    assert (v / "knowledge/projects/x.md") in changed
    x = (v / "knowledge/projects/x.md").read_text()
    assert "drop" not in x and x.count("../people/keep") == 2
    # Idempotent: a second pass finds nothing.
    again = rewrite_links(
        v / "knowledge", v, v / "knowledge/people/drop.md", "people/keep", dry_run=False,
    )
    assert again == []
