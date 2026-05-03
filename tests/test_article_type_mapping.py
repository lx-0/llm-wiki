"""Regression test for M003-S04-T01: `MOCs/ → moc` mapping must stay
in lint.FOLDER_TO_TYPE so the article-type linter recognises the new
MOC layer (and complains if a MOC file accidentally carries the wrong
type frontmatter)."""

from __future__ import annotations


def test_folder_to_type_includes_moc() -> None:
    import lint
    assert lint.FOLDER_TO_TYPE.get("MOCs") == "moc"


def test_folder_to_type_covers_all_substrate_folders() -> None:
    """Sanity: each well-known folder maps to a distinct type identifier."""
    import lint
    expected = {"concepts", "connections", "qa", "people", "projects", "MOCs", "facts"}
    assert expected.issubset(set(lint.FOLDER_TO_TYPE.keys()))
    types = list(lint.FOLDER_TO_TYPE.values())
    assert len(types) == len(set(types)), "duplicate type identifiers in FOLDER_TO_TYPE"
