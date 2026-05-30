"""Golden-diff for the O(N²)→O(N) lint-orphan fix (2026-05-30).

`build_inbound_count_map` (one single-pass replacement) must produce inbound
counts byte-for-byte identical to repeated `count_inbound_links` (the O(N²)
oracle it replaced inside `check_orphan_pages`). This is the behaviour-
preservation proof: same orphan verdicts, just computed once instead of N×N.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _fixture_corpus(tmp_path: Path):
    """Edge cases the two implementations must agree on: a source linking the
    same target twice (counts once), a self-link (excluded), a cross-folder
    relative link, an unresolved link (no edge), a `## Backlinks` footer link
    (full-content read — counted, mirroring the oracle), multiple sources."""
    k = tmp_path / "knowledge"
    _write(k / "concepts" / "a.md", "Body [[b]] and again [[b]] and [[../people/alex]].")
    _write(k / "concepts" / "b.md", "No outgoing links.\n\n## Backlinks\n\n- [[a]]\n")
    _write(k / "concepts" / "c.md", "See [[b]] and [[nonexistent-xyz]].")
    _write(k / "people" / "alex.md", "Self ref [[alex]] should not count.")
    return k, sorted(k.rglob("*.md"))


def _patch_paths(monkeypatch, tmp_path: Path, kdir: Path, arts: list[Path]) -> None:
    from core import paths, utils
    monkeypatch.setattr(utils, "list_wiki_articles", lambda: arts)
    monkeypatch.setattr(utils, "KNOWLEDGE_DIR", kdir)
    monkeypatch.setattr(paths, "ROOT_DIR", tmp_path)


def test_map_matches_oracle_for_every_article(tmp_path, monkeypatch):
    """The golden-diff: for every article, the map-derived inbound count equals
    count_inbound_links(name, exclude_file=article)."""
    from core import utils
    kdir, arts = _fixture_corpus(tmp_path)
    _patch_paths(monkeypatch, tmp_path, kdir, arts)

    inbound_map = utils.build_inbound_count_map()
    for art in arts:
        name = str(art.relative_to(kdir)).replace(".md", "")
        from_map = len(inbound_map.get(name, set()) - {str(art)})
        from_oracle = utils.count_inbound_links(name, exclude_file=art)
        assert from_map == from_oracle, f"{name}: map={from_map} oracle={from_oracle}"


def test_known_inbound_values(tmp_path, monkeypatch):
    """Pin the actual counts so a future refactor of either side can't drift
    them in lock-step undetected."""
    from core import utils
    kdir, arts = _fixture_corpus(tmp_path)
    _patch_paths(monkeypatch, tmp_path, kdir, arts)
    m = utils.build_inbound_count_map()

    def count(name, art):
        return len(m.get(name, set()) - {str(kdir / f"{art}.md")})

    # b is linked by a (deduped from two [[b]]) and c → 2
    assert count("concepts/b", "concepts/b") == 2
    # alex is linked by a's [[../people/alex]]; alex's own [[alex]] is self → 1
    assert count("people/alex", "people/alex") == 1
    # a is linked only by b's footer [[a]] (full-content read) → 1
    assert count("concepts/a", "concepts/a") == 1
    # c has no inbound at all → orphan
    assert count("concepts/c", "concepts/c") == 0


def test_check_orphan_pages_flags_only_true_orphans(tmp_path, monkeypatch):
    """End-to-end through the rewritten check_orphan_pages: only the genuinely
    unlinked, not-in-index article (c) is flagged."""
    import lint
    from core import paths, utils
    kdir, arts = _fixture_corpus(tmp_path)
    _patch_paths(monkeypatch, tmp_path, kdir, arts)
    monkeypatch.setattr(lint, "list_wiki_articles", lambda: arts)
    monkeypatch.setattr(lint, "KNOWLEDGE_DIR", kdir)
    monkeypatch.setattr(lint, "read_wiki_index", lambda: "")  # nothing in index

    flagged = {i["file"] for i in lint.check_orphan_pages()}
    assert flagged == {"concepts/c.md"}, flagged
