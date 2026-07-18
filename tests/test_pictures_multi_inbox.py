"""Multi-path `personal.picture_inbox` regression tests (2026-05-28).

Verifies that the type relaxation from `str` to `str | list[str]` works
in both shapes:

- Back-compat: existing operators with `picture_inbox: "<single-path>"`
  configs keep working unchanged.
- Multi-path: operators can now point at several inbox directories at
  once (e.g. an existing iCloud-Drive folder + an inbox_bridges-mirrored
  Google Drive folder). The collector scans every configured path,
  aggregates files into one batch, and degrades gracefully when one of
  the paths doesn't exist yet (Drive offline, mirror not yet populated).

Vision calls are mocked — the focus is on the pre-vision routing layer,
not the gemma4 pipeline.
"""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def pictures_mod(tmp_path, monkeypatch):
    """Reload the collector against a tmpdir RAW_DIR so the archive zone
    + batch report don't write into the operator's vault."""
    from core import paths as paths_mod

    vault_raw = tmp_path / "vault" / "raw"
    vault_raw.mkdir(parents=True)
    monkeypatch.setattr(paths_mod, "RAW_DIR", vault_raw)

    from collectors import pictures as mod
    importlib.reload(mod)
    return mod


# ── _inbox_paths: shape interpretation ────────────────────────────


def test_inbox_paths_empty_string(monkeypatch, pictures_mod):
    from core.config import CONFIG
    monkeypatch.setattr(CONFIG.personal, "picture_inbox", "")
    assert pictures_mod._inbox_paths() == []


def test_inbox_paths_single_string(monkeypatch, pictures_mod, tmp_path):
    from core.config import CONFIG
    p = tmp_path / "a"
    monkeypatch.setattr(CONFIG.personal, "picture_inbox", str(p))
    paths = pictures_mod._inbox_paths()
    assert len(paths) == 1
    assert paths[0] == p


def test_inbox_paths_list_form(monkeypatch, pictures_mod, tmp_path):
    from core.config import CONFIG
    p1, p2 = tmp_path / "a", tmp_path / "b"
    monkeypatch.setattr(CONFIG.personal, "picture_inbox", [str(p1), str(p2)])
    paths = pictures_mod._inbox_paths()
    assert paths == [p1, p2]


def test_inbox_paths_list_skips_blanks(monkeypatch, pictures_mod, tmp_path):
    """Operator can leave dead entries in the list without breaking the scan."""
    from core.config import CONFIG
    p = tmp_path / "real"
    monkeypatch.setattr(CONFIG.personal, "picture_inbox", ["", str(p), "   ", None])
    paths = pictures_mod._inbox_paths()
    assert paths == [p]


def test_inbox_paths_empty_list(monkeypatch, pictures_mod):
    from core.config import CONFIG
    monkeypatch.setattr(CONFIG.personal, "picture_inbox", [])
    assert pictures_mod._inbox_paths() == []


def test_inbox_paths_expands_tilde(monkeypatch, pictures_mod):
    from core.config import CONFIG
    monkeypatch.setattr(CONFIG.personal, "picture_inbox", ["~/foo", "~/bar"])
    paths = pictures_mod._inbox_paths()
    assert all("~" not in str(p) for p in paths)
    assert len(paths) == 2


# ── is_configured: any path-existence wins ────────────────────────


def test_is_configured_false_when_all_paths_empty(monkeypatch, pictures_mod):
    from core.config import CONFIG
    monkeypatch.setattr(CONFIG.personal, "picture_inbox", "")
    coll = pictures_mod.PicturesCollector()
    assert coll.is_configured() is False


def test_is_configured_false_when_no_path_exists(monkeypatch, pictures_mod, tmp_path):
    from core.config import CONFIG
    monkeypatch.setattr(
        CONFIG.personal,
        "picture_inbox",
        [str(tmp_path / "nope-a"), str(tmp_path / "nope-b")],
    )
    coll = pictures_mod.PicturesCollector()
    assert coll.is_configured() is False


def test_is_configured_true_when_any_path_exists(monkeypatch, pictures_mod, tmp_path):
    from core.config import CONFIG
    real = tmp_path / "real"
    real.mkdir()
    monkeypatch.setattr(
        CONFIG.personal,
        "picture_inbox",
        [str(tmp_path / "missing"), str(real)],
    )
    coll = pictures_mod.PicturesCollector()
    assert coll.is_configured() is True


# ── run: graceful no-source + missing-inbox handling ───────────────


def test_run_no_inbox_configured(monkeypatch, pictures_mod):
    from core.config import CONFIG
    monkeypatch.setattr(CONFIG.personal, "picture_inbox", "")
    result = pictures_mod.PicturesCollector().run()
    assert "not configured" in result.message


def test_run_skips_missing_path_warns_keeps_going(monkeypatch, pictures_mod, tmp_path, caplog):
    from core.config import CONFIG
    real = tmp_path / "real"
    real.mkdir()
    missing = tmp_path / "missing"
    monkeypatch.setattr(
        CONFIG.personal,
        "picture_inbox",
        [str(missing), str(real)],
    )
    with caplog.at_level("WARNING"):
        result = pictures_mod.PicturesCollector().run()
    assert "no new pictures" in result.message  # real path is empty
    assert any("missing" in r.message and "not found" in r.message for r in caplog.records)


def test_run_all_vision_failed_message_is_multi_inbox_aware(monkeypatch, pictures_mod, tmp_path):
    """Regression: the "no pictures processed" message must describe the whole
    multi-inbox scope, not a stale single loop variable.

    When 2+ inboxes are configured and every vision call fails, `results`
    stays empty and the collector returns the no-success message. It used to
    interpolate `inbox` — the leftover loop variable bound to the LAST inbox
    scanned — naming one path while the run covered several. The sibling
    no-source / dry-run messages already compute a multi-inbox label; this
    path must too.
    """
    from core.config import CONFIG
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / "1.jpg").write_bytes(b"\xff\xd8\xff")
    (b / "2.jpg").write_bytes(b"\xff\xd8\xff")

    monkeypatch.setattr(CONFIG.personal, "picture_inbox", [str(a), str(b)])
    # Every vision call fails -> results stays empty -> no-success return path.
    monkeypatch.setattr(pictures_mod, "describe_picture", lambda src: None)
    monkeypatch.setattr(pictures_mod, "_make_thumbnail", lambda src: None)
    monkeypatch.setattr(pictures_mod.ollama_client, "is_reachable", lambda: True)

    result = pictures_mod.PicturesCollector().run()

    assert result.files_written == ()
    # Describes the whole scope, not just the last-scanned inbox path.
    assert "2 configured inbox(es)" in result.message
    assert str(b) not in result.message


def test_run_aggregates_sources_across_paths(monkeypatch, pictures_mod, tmp_path):
    from core.config import CONFIG
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / "1.jpg").write_bytes(b"\xff\xd8\xff")
    (b / "2.jpg").write_bytes(b"\xff\xd8\xff")

    monkeypatch.setattr(CONFIG.personal, "picture_inbox", [str(a), str(b)])
    monkeypatch.setattr(pictures_mod, "describe_picture", lambda src: {
        "scene_description": "x", "objects": [], "action": "",
        "text_visible": "", "relevance": "ephemeral", "tags": [],
        "people_present": False, "raw_response": "",
    })
    monkeypatch.setattr(pictures_mod, "_make_thumbnail", lambda src: None)
    monkeypatch.setattr(pictures_mod.ollama_client, "is_reachable", lambda: True)

    result = pictures_mod.PicturesCollector().run()
    assert "2 picture(s) processed" in result.message
    # Both originals end up in the central archive zone — proves the
    # archive-move loop walked over both source paths.
    archive = pictures_mod.MOBILE_ARCHIVE_DIR
    assert (archive / "1.jpg").exists()
    assert (archive / "2.jpg").exists()
    # Source folders drained.
    assert list(a.iterdir()) == []
    assert list(b.iterdir()) == []
