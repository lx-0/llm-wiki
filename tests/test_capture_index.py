"""Tests for the capture index — capture_id → {source_path, created, status}
map written at ingest, consumed by the correction loop (M025-S01-T03)."""

from __future__ import annotations

import pytest


@pytest.fixture
def index_env(tmp_path, monkeypatch):
    """Isolate the index + lock paths into tmp_path so tests never touch the
    real vault state."""
    from core import capture_index as ci

    monkeypatch.setattr(ci, "CAPTURE_INDEX_FILE", tmp_path / "state" / "capture_index.json")
    monkeypatch.setattr(ci, "_LOCK_FILE", tmp_path / "state" / "capture_index.lock")
    return ci


def test_record_adds_entry(index_env):
    ci = index_env
    added = ci.record(
        "abc123def456",
        source_path="raw/captures/capture-abc123def456.md",
        created="2026-05-23T10:00:00+02:00",
    )
    assert added is True
    idx = ci.load()
    assert idx["abc123def456"] == {
        "source_path": "raw/captures/capture-abc123def456.md",
        "created": "2026-05-23T10:00:00+02:00",
        "status": "open",
    }


def test_record_is_idempotent(index_env):
    ci = index_env
    assert ci.record("abc", source_path="raw/captures/capture-abc.md", created="t1") is True
    # Second record of the same id is a no-op and reports it.
    assert ci.record("abc", source_path="raw/captures/capture-abc.md", created="t2") is False
    idx = ci.load()
    assert len(idx) == 1
    assert idx["abc"]["created"] == "t1"  # original entry preserved, not clobbered


def test_reingest_preserves_superseded_status(index_env):
    """A re-drop of identical content (same capture-ID) must NOT reset a status
    an operator correction (S03) already flipped to superseded."""
    ci = index_env
    ci.record("abc", source_path="raw/captures/capture-abc.md", created="t1")

    # Simulate S03 marking the interpretation superseded.
    from core.utils import save_json_state

    idx = ci.load()
    idx["abc"]["status"] = ci.STATUS_SUPERSEDED
    save_json_state(ci.CAPTURE_INDEX_FILE, idx)

    # Re-ingest (operator re-drops the same note).
    added = ci.record("abc", source_path="raw/captures/capture-abc.md", created="t3")
    assert added is False
    assert ci.load()["abc"]["status"] == ci.STATUS_SUPERSEDED


def test_load_empty_when_absent(index_env):
    assert index_env.load() == {}


def test_load_tolerates_corrupt_json(index_env):
    ci = index_env
    ci.CAPTURE_INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    ci.CAPTURE_INDEX_FILE.write_text("{ this is not valid json", encoding="utf-8")
    # Corrupt / partially-written file must not crash the ingest path.
    assert ci.load() == {}


def test_distinct_ids_coexist(index_env):
    ci = index_env
    ci.record("aaa", source_path="raw/captures/capture-aaa.md", created="t1")
    ci.record("bbb", source_path="raw/captures/capture-bbb.md", created="t2")
    assert set(ci.load()) == {"aaa", "bbb"}


# --- M025-S02-T01: capture_id → article resolution -------------------------

def _write_article(kdir, rel, compiled_from):
    import yaml as _yaml

    p = kdir / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    fm = _yaml.safe_dump({"type": "person", "compiled_from": compiled_from}, sort_keys=False).strip()
    p.write_text(f"---\n{fm}\n---\n# {p.stem}\nBody.\n", encoding="utf-8")
    return p


def test_resolve_articles_joins_compiled_from(index_env, tmp_path):
    ci = index_env
    ci.record("abc123", source_path="raw/captures/capture-abc123.md", created="t1")
    ci.record("def456", source_path="raw/captures/capture-def456.md", created="t2")  # never compiled

    kdir = tmp_path / "knowledge"
    _write_article(kdir, "people/sid.md", ["raw/captures/capture-abc123.md", "raw/notes/email/x.md"])
    _write_article(kdir, "concepts/x.md", "raw/notes/email/y.md")  # string form, no capture

    res = ci.resolve_articles(knowledge_dir=kdir)
    assert res["abc123"] == ["knowledge/people/sid.md"]
    assert res["def456"] == []  # captured but not (yet) compiled


def test_resolve_articles_basename_match_and_multiple(index_env, tmp_path):
    ci = index_env
    ci.record("xyz", source_path="raw/captures/capture-xyz.md", created="t1")
    kdir = tmp_path / "knowledge"
    _write_article(kdir, "projects/a.md", ["raw/captures/capture-xyz.md"])
    _write_article(kdir, "projects/b.md", ["./raw/captures/capture-xyz.md"])  # differing prefix
    _write_article(kdir, "facts/n.md", "raw/notes/x.md")  # no match
    res = ci.resolve_articles(knowledge_dir=kdir)
    assert sorted(res["xyz"]) == ["knowledge/projects/a.md", "knowledge/projects/b.md"]


def test_resolve_articles_empty_index_and_missing_dir(index_env, tmp_path):
    ci = index_env
    assert ci.resolve_articles(knowledge_dir=tmp_path / "knowledge") == {}  # empty index → {}
    ci.record("q", source_path="raw/captures/capture-q.md", created="t1")
    assert ci.resolve_articles(knowledge_dir=tmp_path / "nope") == {"q": []}  # absent dir → no crash
