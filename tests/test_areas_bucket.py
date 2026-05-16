"""Test the 7th knowledge bucket: knowledge/areas/ for ongoing responsibilities.

Spec: .ytstack/backlog/areas-bucket.md.

Covers:
- AREAS_DIR is declared on core.paths and points at <ROOT>/knowledge/areas
- core.utils.WIKI_SUBDIRS includes AREAS_DIR so list_wiki_articles() enumerates it
- lint.FOLDER_TO_TYPE maps "areas" → "area"
- pin.TYPE_TO_MOC maps "area" → "areas"
- check_area_status accepts the active|dormant|retired enum and rejects others
"""

from __future__ import annotations

from pathlib import Path

import pytest


def test_areas_dir_declared_and_under_knowledge() -> None:
    from core import paths
    assert hasattr(paths, "AREAS_DIR"), "core.paths.AREAS_DIR must exist"
    assert paths.AREAS_DIR == paths.KNOWLEDGE_DIR / "areas"


def test_wiki_subdirs_includes_areas() -> None:
    """list_wiki_articles() must enumerate knowledge/areas/."""
    from core import utils
    from core.paths import AREAS_DIR
    assert AREAS_DIR in utils.WIKI_SUBDIRS, "WIKI_SUBDIRS must include AREAS_DIR"


def test_list_wiki_articles_picks_up_areas(tmp_path, monkeypatch) -> None:
    """End-to-end: file under knowledge/areas/ shows up in list_wiki_articles."""
    from core import paths, utils

    # Build a fake vault layout
    fake_areas = tmp_path / "knowledge" / "areas"
    fake_areas.mkdir(parents=True)
    fake_md = fake_areas / "example-area.md"
    fake_md.write_text(
        "---\ntype: area\nstatus: active\n---\n# Example Area\n",
        encoding="utf-8",
    )

    # Point WIKI_SUBDIRS at our fake areas dir
    monkeypatch.setattr(utils, "WIKI_SUBDIRS", [fake_areas])
    found = utils.list_wiki_articles()
    assert fake_md in found


def test_lint_folder_to_type_maps_areas_to_area() -> None:
    import lint
    assert lint.FOLDER_TO_TYPE.get("areas") == "area"


def test_pin_type_to_moc_routes_area() -> None:
    """pin.py routes `type: area` articles to the `areas` MOC."""
    import pin
    assert pin.TYPE_TO_MOC.get("area") == "areas"


def test_check_area_status_accepts_valid_enum(tmp_path, monkeypatch) -> None:
    """active|dormant|retired must all pass check_area_status."""
    import lint
    from core import paths

    fake_knowledge = tmp_path / "knowledge"
    fake_areas = fake_knowledge / "areas"
    fake_areas.mkdir(parents=True)

    for status in ("active", "dormant", "retired"):
        (fake_areas / f"{status}-area.md").write_text(
            f"---\ntype: area\nstatus: {status}\n---\n# {status}\n",
            encoding="utf-8",
        )

    monkeypatch.setattr(paths, "KNOWLEDGE_DIR", fake_knowledge)
    monkeypatch.setattr(lint, "KNOWLEDGE_DIR", fake_knowledge)
    issues = lint.check_area_status()
    assert issues == [], f"valid statuses must produce no issues, got {issues}"


def test_check_area_status_rejects_invalid_value(tmp_path, monkeypatch) -> None:
    import lint
    from core import paths

    fake_knowledge = tmp_path / "knowledge"
    fake_areas = fake_knowledge / "areas"
    fake_areas.mkdir(parents=True)
    (fake_areas / "bad.md").write_text(
        "---\ntype: area\nstatus: in-progress\n---\n# Bad\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(paths, "KNOWLEDGE_DIR", fake_knowledge)
    monkeypatch.setattr(lint, "KNOWLEDGE_DIR", fake_knowledge)
    issues = lint.check_area_status()
    assert len(issues) == 1
    assert issues[0]["check"] == "area_invalid_status"
    assert issues[0]["severity"] == "error"


def test_check_area_status_flags_missing_status(tmp_path, monkeypatch) -> None:
    import lint
    from core import paths

    fake_knowledge = tmp_path / "knowledge"
    fake_areas = fake_knowledge / "areas"
    fake_areas.mkdir(parents=True)
    (fake_areas / "no-status.md").write_text(
        "---\ntype: area\n---\n# Missing\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(paths, "KNOWLEDGE_DIR", fake_knowledge)
    monkeypatch.setattr(lint, "KNOWLEDGE_DIR", fake_knowledge)
    issues = lint.check_area_status()
    assert len(issues) == 1
    assert issues[0]["check"] == "area_missing_status"
    assert issues[0]["severity"] == "error"


def test_check_area_status_ignores_non_area_files(tmp_path, monkeypatch) -> None:
    """Files in areas/ without type: area are skipped (check_article_type handles them)."""
    import lint
    from core import paths

    fake_knowledge = tmp_path / "knowledge"
    fake_areas = fake_knowledge / "areas"
    fake_areas.mkdir(parents=True)
    (fake_areas / "wrong-type.md").write_text(
        "---\ntype: concept\n---\n# Wrong type — handled elsewhere\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(paths, "KNOWLEDGE_DIR", fake_knowledge)
    monkeypatch.setattr(lint, "KNOWLEDGE_DIR", fake_knowledge)
    issues = lint.check_area_status()
    assert issues == []


def test_check_area_status_returns_empty_when_no_areas_dir(tmp_path, monkeypatch) -> None:
    """Engine must not crash on vaults that haven't created knowledge/areas/ yet."""
    import lint
    from core import paths

    fake_knowledge = tmp_path / "knowledge"
    fake_knowledge.mkdir(parents=True)
    # NOTE: no areas/ subdir

    monkeypatch.setattr(paths, "KNOWLEDGE_DIR", fake_knowledge)
    monkeypatch.setattr(lint, "KNOWLEDGE_DIR", fake_knowledge)
    assert lint.check_area_status() == []
