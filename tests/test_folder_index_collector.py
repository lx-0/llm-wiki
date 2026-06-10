"""Tests for the body-blind folder-index walker (collectors/folder_index.py).

M027-S02-T01: pure walk logic over one `personal.watched_folders` entry
(kind=local). The walker builds the minimum-viable digest — depth-capped
directory tree + top-N-recent-by-mtime — WITHOUT ever opening a file
(body-blind invariant: `os.scandir` + `stat(follow_symlinks=False)` only).

Names/paths land in the model as-is — NO sanitization/masking (DECISIONS
2026-06-07: the metadata index is built freely; the human-approval walk in
S03 is the content gate).
"""

from __future__ import annotations

import os
import unicodedata

import pytest

from collectors.folder_index import walk_root


def _entry(root, **kw):
    e = {"id": "test-root", "kind": "local", "path": str(root)}
    e.update(kw)
    return e


def _rels(entries):
    return [e.rel_path for e in entries]


def _nfc_rels(entries):
    return [unicodedata.normalize("NFC", e.rel_path) for e in entries]


@pytest.fixture
def tree(tmp_path):
    """Fixture tree: nested dirs, a dotfile, an excludable subtree, a
    too-deep subtree, umlaut/space filenames."""
    root = tmp_path / "watched"
    (root / "a-dir").mkdir(parents=True)
    (root / "a-dir" / "inner.txt").write_text("inner")
    (root / "b-dir" / "nested" / "deep").mkdir(parents=True)
    (root / "b-dir" / "nested" / "deep" / "toodeep.txt").write_text("deep")
    (root / "b-dir" / "nested" / "mid.txt").write_text("mid")
    (root / "excluded-dir").mkdir()
    (root / "excluded-dir" / "secret.txt").write_text("s")
    (root / ".dotfile").write_text("dot")
    (root / "ümlaut file ä.txt").write_text("u")
    (root / "afile.txt").write_text("a")
    (root / "zfile.md").write_text("z")
    return root


def test_body_blind_walker_never_opens_files(tree, monkeypatch):
    """The walker must survive a poisoned builtins.open — it never reads bodies."""

    def _boom(*args, **kwargs):  # pragma: no cover - must never fire
        raise AssertionError("body-blind invariant violated: open() was called")

    monkeypatch.setattr("builtins.open", _boom)
    idx = walk_root(_entry(tree), max_depth=10, recent_n=5)
    assert idx.counts["files"] > 0
    assert idx.counts["errors"] == 0


def test_depth_cap_honored_and_counted(tree):
    # max_depth=2: entries at depth 1+2 enumerated; dirs at depth 2 not descended.
    idx = walk_root(_entry(tree), max_depth=2, recent_n=5)
    rels = _rels(idx.tree)
    assert os.path.join("b-dir", "nested") in rels
    assert os.path.join("b-dir", "nested", "mid.txt") not in rels
    assert os.path.join("b-dir", "nested", "deep") not in rels
    assert idx.counts["skipped_depth"] == 1  # b-dir/nested not descended

    # max_depth=3: mid.txt visible, `deep` dir enumerated but not descended.
    idx3 = walk_root(_entry(tree), max_depth=3, recent_n=5)
    rels3 = _rels(idx3.tree)
    assert os.path.join("b-dir", "nested", "mid.txt") in rels3
    assert os.path.join("b-dir", "nested", "deep") in rels3
    assert os.path.join("b-dir", "nested", "deep", "toodeep.txt") not in rels3
    assert idx3.counts["skipped_depth"] == 1  # deep not descended


def test_include_exclude_globs_exclude_wins(tree):
    # Excluded dir: absent from tree, not descended, counted.
    idx = walk_root(
        _entry(tree, exclude=["excluded-dir"]), max_depth=10, recent_n=5
    )
    rels = _rels(idx.tree)
    assert "excluded-dir" not in rels
    assert os.path.join("excluded-dir", "secret.txt") not in rels
    assert idx.counts["skipped_excluded"] >= 1

    # include filters files; exclude wins over include.
    idx2 = walk_root(
        _entry(tree, include=["*.txt"], exclude=["afile.txt"]),
        max_depth=10,
        recent_n=5,
    )
    rels2 = _rels(idx2.tree)
    assert "zfile.md" not in rels2  # not in include
    assert "afile.txt" not in rels2  # in include AND exclude -> exclude wins
    assert os.path.join("a-dir", "inner.txt") in rels2


def test_recent_is_top_n_by_mtime_desc_deterministic(tree):
    for rel in (
        ".dotfile",
        os.path.join("b-dir", "nested", "mid.txt"),
        os.path.join("b-dir", "nested", "deep", "toodeep.txt"),
        os.path.join("excluded-dir", "secret.txt"),
    ):
        os.utime(tree / rel, (500, 500))  # background noise, older than the pins
    os.utime(tree / "afile.txt", (1000, 1000))
    os.utime(tree / "ümlaut file ä.txt", (1000, 1000))  # mtime tie with afile
    os.utime(tree / "zfile.md", (2000, 2000))
    os.utime(tree / "a-dir" / "inner.txt", (3000, 3000))

    idx = walk_root(_entry(tree), max_depth=10, recent_n=3)
    assert len(idx.recent) == 3
    assert all(not e.is_dir for e in idx.recent)
    assert _rels(idx.recent)[0] == os.path.join("a-dir", "inner.txt")
    assert _rels(idx.recent)[1] == "zfile.md"
    # tie at 1000 broken by rel_path ascending: "afile.txt" < "ümlaut…"
    assert _rels(idx.recent)[2] == "afile.txt"

    # Determinism: same fixture in, same model out (tree + recent + counts).
    idx_again = walk_root(_entry(tree), max_depth=10, recent_n=3)
    assert idx_again.tree == idx.tree
    assert idx_again.recent == idx.recent
    assert idx_again.counts == idx.counts


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores permission bits")
def test_permission_denied_fails_soft(tree):
    denied = tree / "denied"
    denied.mkdir()
    (denied / "hidden.txt").write_text("x")
    denied.chmod(0o000)
    try:
        idx = walk_root(_entry(tree), max_depth=10, recent_n=5)
    finally:
        denied.chmod(0o755)
    assert idx.counts["errors"] == 1
    rels = _rels(idx.tree)
    assert "denied" in rels  # the dir itself was statable
    assert os.path.join("denied", "hidden.txt") not in rels
    assert "afile.txt" in rels  # walk completed past the error


def test_filenames_land_unmasked(tree):
    idx = walk_root(_entry(tree), max_depth=10, recent_n=5)
    rels = _nfc_rels(idx.tree)
    assert "ümlaut file ä.txt" in rels  # umlauts + spaces verbatim, no masking
    assert ".dotfile" in rels  # dotfiles not hidden either
    by_rel = {
        unicodedata.normalize("NFC", e.rel_path): e for e in idx.tree
    }
    assert by_rel["ümlaut file ä.txt"].ext == ".txt"
    assert by_rel["ümlaut file ä.txt"].is_dir is False
    assert by_rel["a-dir"].is_dir is True
    assert by_rel["a-dir"].size is None
    assert by_rel["afile.txt"].size == 1


def test_nonexistent_root_raises_value_error(tmp_path):
    with pytest.raises(ValueError):
        walk_root(_entry(tmp_path / "does-not-exist"), max_depth=2, recent_n=5)
