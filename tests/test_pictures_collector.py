"""Smoke test for the pictures collector archive-location invariant (M022-S02).

The collector calls a vision LLM (Gemma4) on each image, which is too heavy
to wire into the unit suite. This file exercises only the routing
invariant: after a successful run, the original PNG lands under
`raw/inbox-mobile/pictures/` (M022 vault audit zone) — never under
`<picture_inbox>/.processed/` (the pre-M022 location).

Full vision-pipeline coverage is intentionally out of scope here; the
operator-facing acceptance test is "drop a photo in the inbox, see the
batch report on the next compile run" — that's a manual probe, not a unit
test.
"""

from __future__ import annotations

import importlib
from unittest import mock

import pytest


@pytest.fixture
def pictures_env(tmp_path, monkeypatch):
    """Tmpdir inbox + tmpdir vault, pictures collector reloaded against patched RAW_DIR."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    vault_raw = tmp_path / "vault" / "raw"
    vault_raw.mkdir(parents=True)

    from core.config import CONFIG
    from core import paths as paths_mod

    monkeypatch.setattr(CONFIG.personal, "picture_inbox", str(inbox))
    monkeypatch.setattr(paths_mod, "RAW_DIR", vault_raw)

    from collectors import pictures as pictures_mod
    importlib.reload(pictures_mod)

    return pictures_mod, inbox, vault_raw


def test_picture_archive_lands_in_vault_not_inbox_processed(pictures_env, monkeypatch):
    pictures_mod, inbox, vault_raw = pictures_env

    # Drop a fake PNG (vision call is mocked, so bytes content doesn't matter).
    (inbox / "IMG_1234.png").write_bytes(b"\x89PNG\r\n\x1a\n_FAKE_")

    # Stub the vision-call helpers so the test doesn't talk to Ollama.
    monkeypatch.setattr(
        pictures_mod,
        "describe_picture",
        lambda src: {
            "scene_description": "a fake test image",
            "objects": [],
            "action": "",
            "text_visible": "",
            "keep": True,
        },
    )
    monkeypatch.setattr(pictures_mod, "_make_thumbnail", lambda src: None)
    # Bypass the Ollama-reachable preflight check.
    monkeypatch.setattr(pictures_mod.ollama_client, "is_reachable", lambda: True)

    coll = pictures_mod.PicturesCollector()
    coll.run()

    # Archive landed in the vault audit zone.
    archive = pictures_mod.MOBILE_ARCHIVE_DIR
    assert archive.is_dir(), f"audit archive missing: {archive}"
    assert (archive / "IMG_1234.png").exists(), "original PNG missing from vault audit zone"

    # Regression guard: the legacy <inbox>/.processed/ must NOT have been recreated.
    assert not (inbox / ".processed").exists(), "legacy .processed/ subdir was recreated"
