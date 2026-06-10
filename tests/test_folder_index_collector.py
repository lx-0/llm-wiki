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

import collectors.folder_index as folder_index
from collectors.folder_index import (
    index_signature,
    render_index,
    sync_root,
    walk_root,
    write_index,
)


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


# --- T02: render + write -------------------------------------------------


def test_render_index_frontmatter_and_sections(tree):
    idx = walk_root(_entry(tree), max_depth=10, recent_n=3)
    out = render_index(idx, max_tree_entries=1000)
    assert out.startswith("---\n")
    assert "type: folder-index" in out
    assert "root_id: test-root" in out
    assert "truncated: false" in out
    # counts flattened into frontmatter
    assert f"files: {idx.counts['files']}" in out
    assert f"errors: {idx.counts['errors']}" in out
    assert "## Recent changes" in out
    assert "## Tree" in out
    # a recent line carries the backticked rel_path
    recent_section = out.split("## Recent changes", 1)[1].split("## Tree", 1)[0]
    assert "`" in recent_section
    assert len(idx.recent) == 3


def test_render_index_deterministic(tree):
    idx = walk_root(_entry(tree), max_depth=10, recent_n=3)
    assert render_index(idx, max_tree_entries=50) == render_index(
        idx, max_tree_entries=50
    )


def test_render_index_tree_size_cap(tree):
    idx = walk_root(_entry(tree), max_depth=10, recent_n=3)
    total = len(idx.tree)  # fixture: 5 dirs + 8 files = 13
    assert total == 13
    out = render_index(idx, max_tree_entries=3)
    assert "truncated: true" in out
    assert f"{total - 3} more entries omitted" in out
    # recent section unaffected by the tree cap
    recent_section = out.split("## Recent changes", 1)[1].split("## Tree", 1)[0]
    assert recent_section.count("- `") == 3


def test_render_index_names_unmasked(tree):
    idx = walk_root(_entry(tree), max_depth=10, recent_n=3)
    out = unicodedata.normalize("NFC", render_index(idx, max_tree_entries=1000))
    assert "ümlaut file ä.txt" in out
    assert ".dotfile" in out


# --- T03: delta-awareness -------------------------------------------------


def _sync_env(monkeypatch, tmp_path):
    """Isolate INDEX_DIR + STATE_FILE so sync tests never touch the repo."""
    index_dir = tmp_path / "raw-index"
    state_file = tmp_path / "state" / "folder-index.json"
    monkeypatch.setattr(folder_index, "INDEX_DIR", index_dir)
    monkeypatch.setattr(folder_index, "STATE_FILE", state_file)
    return index_dir, state_file


def test_index_signature_stable_then_changes_on_mtime(tree):
    sig_a = index_signature(walk_root(_entry(tree), max_depth=10, recent_n=3))
    sig_b = index_signature(walk_root(_entry(tree), max_depth=10, recent_n=3))
    assert sig_a == sig_b  # generated_at differs between walks — must not matter
    os.utime(tree / "afile.txt", (2000, 2000))
    sig_c = index_signature(walk_root(_entry(tree), max_depth=10, recent_n=3))
    assert sig_c != sig_a


def test_sync_root_writes_first_then_skips_unchanged(tree, tmp_path, monkeypatch):
    import json

    index_dir, state_file = _sync_env(monkeypatch, tmp_path)
    first = sync_root(_entry(tree), max_depth=10, recent_n=3, max_tree_entries=100)
    assert first.written is True
    assert first.path == index_dir / "test-root.md"
    assert first.path.exists()
    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state["test-root"]["signature"] == first.signature

    second = sync_root(_entry(tree), max_depth=10, recent_n=3, max_tree_entries=100)
    assert second.written is False
    assert second.reason == "unchanged"


def test_sync_root_rewrites_on_force_and_on_deleted_digest(
    tree, tmp_path, monkeypatch
):
    _sync_env(monkeypatch, tmp_path)
    first = sync_root(_entry(tree), max_depth=10, recent_n=3, max_tree_entries=100)
    # operator deleted the digest — unchanged signature must NOT mask that
    first.path.unlink()
    rewrite = sync_root(_entry(tree), max_depth=10, recent_n=3, max_tree_entries=100)
    assert rewrite.written is True
    assert rewrite.path.exists()
    forced = sync_root(
        _entry(tree), max_depth=10, recent_n=3, max_tree_entries=100, force=True
    )
    assert forced.written is True


def test_sync_root_corrupt_state_fails_soft(tree, tmp_path, monkeypatch):
    _sync_env(monkeypatch, tmp_path)
    state_file = tmp_path / "state" / "folder-index.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text("{not valid json", encoding="utf-8")
    result = sync_root(_entry(tree), max_depth=10, recent_n=3, max_tree_entries=100)
    assert result.written is True  # corrupt state -> full rebuild, no crash


# --- T04: CLI entry (`wiki index`) ----------------------------------------


def _patch_watched(monkeypatch, entries):
    from core.config import CONFIG

    monkeypatch.setattr(CONFIG.personal, "watched_folders", entries)


def _second_tree(tmp_path):
    root = tmp_path / "second"
    root.mkdir()
    (root / "f.txt").write_text("f")
    return root


def test_cli_syncs_local_roots_and_skips_smb(tree, tmp_path, monkeypatch):
    index_dir, _ = _sync_env(monkeypatch, tmp_path)
    second = _second_tree(tmp_path)
    _patch_watched(
        monkeypatch,
        [
            _entry(tree),
            {"id": "second-root", "kind": "local", "path": str(second)},
            {"id": "nas-docs", "kind": "smb", "share": "//nas1/docs"},
        ],
    )
    assert folder_index.main([]) == 0
    assert (index_dir / "test-root.md").exists()
    assert (index_dir / "second-root.md").exists()
    assert not (index_dir / "nas-docs.md").exists()  # smb deferred to S06
    # second run takes the unchanged path and still exits 0
    assert folder_index.main([]) == 0


def test_cli_single_root_selection_and_unknown_id(tree, tmp_path, monkeypatch):
    index_dir, _ = _sync_env(monkeypatch, tmp_path)
    second = _second_tree(tmp_path)
    _patch_watched(
        monkeypatch,
        [
            _entry(tree),
            {"id": "second-root", "kind": "local", "path": str(second)},
        ],
    )
    assert folder_index.main(["second-root"]) == 0
    assert (index_dir / "second-root.md").exists()
    assert not (index_dir / "test-root.md").exists()
    assert folder_index.main(["no-such-root"]) == 1


def test_cli_force_rewrites_unchanged_tree(tree, tmp_path, monkeypatch):
    import json

    _, state_file = _sync_env(monkeypatch, tmp_path)
    _patch_watched(monkeypatch, [_entry(tree)])
    assert folder_index.main([]) == 0
    before = json.loads(state_file.read_text(encoding="utf-8"))
    assert folder_index.main(["--force"]) == 0
    after = json.loads(state_file.read_text(encoding="utf-8"))
    assert (
        after["test-root"]["last_indexed_at"]
        != before["test-root"]["last_indexed_at"]
    )


def test_cli_failing_root_fails_soft_but_exits_nonzero(
    tree, tmp_path, monkeypatch
):
    index_dir, _ = _sync_env(monkeypatch, tmp_path)
    _patch_watched(
        monkeypatch,
        [
            {"id": "ghost", "kind": "local", "path": str(tmp_path / "missing")},
            _entry(tree),
        ],
    )
    assert folder_index.main([]) == 1  # one root failed
    assert (index_dir / "test-root.md").exists()  # ...but the good one synced


def test_cli_no_local_roots_is_friendly_noop(tmp_path, monkeypatch):
    _sync_env(monkeypatch, tmp_path)
    _patch_watched(monkeypatch, [])
    assert folder_index.main([]) == 0


def test_write_index_one_digest_per_root(tree, tmp_path, monkeypatch):
    index_dir = tmp_path / "raw-index"
    monkeypatch.setattr(folder_index, "INDEX_DIR", index_dir)
    idx = walk_root(_entry(tree), max_depth=10, recent_n=3)
    path = write_index(idx, max_tree_entries=1000)
    assert path == index_dir / "test-root.md"
    assert path.read_text(encoding="utf-8") == render_index(
        idx, max_tree_entries=1000
    )
    # re-write overwrites: still exactly one digest for this root
    write_index(idx, max_tree_entries=1000)
    assert [p.name for p in index_dir.iterdir()] == ["test-root.md"]
