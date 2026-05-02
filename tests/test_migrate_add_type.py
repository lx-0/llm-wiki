"""Pure-function tests for the type: backfill migration."""

from __future__ import annotations


def test_needs_migration_missing_frontmatter() -> None:
    import migrate_add_type as m

    change, reason = m.needs_migration("# Just a heading\n\nbody\n", "concept")
    assert change is True
    assert reason == "add-frontmatter"


def test_needs_migration_missing_type() -> None:
    import migrate_add_type as m

    fm = '---\ntitle: "X"\ntags: []\n---\nbody\n'
    change, reason = m.needs_migration(fm, "concept")
    assert change is True
    assert reason == "add-type"


def test_needs_migration_wrong_type() -> None:
    import migrate_add_type as m

    fm = '---\ntitle: "X"\ntype: project\n---\nbody\n'
    change, reason = m.needs_migration(fm, "concept")
    assert change is True
    assert "project → concept" in reason


def test_needs_migration_correct() -> None:
    import migrate_add_type as m

    fm = '---\ntitle: "X"\ntype: concept\n---\nbody\n'
    change, reason = m.needs_migration(fm, "concept")
    assert change is False


def test_apply_migration_inserts_after_title() -> None:
    import migrate_add_type as m

    src = '---\ntitle: "X"\ntags: []\n---\nbody\n'
    out = m.apply_migration(src, "concept")
    assert "type: concept" in out
    # title comes before type, type comes before tags
    assert out.index("title:") < out.index("type:") < out.index("tags:")
    assert out.endswith("body\n")


def test_apply_migration_corrects_existing_wrong_type() -> None:
    import migrate_add_type as m

    src = '---\ntitle: "X"\ntype: project\ntags: []\n---\nbody\n'
    out = m.apply_migration(src, "concept")
    assert "type: concept" in out
    assert "type: project" not in out
    # Order preserved: title / type / tags
    assert out.index("title:") < out.index("type:") < out.index("tags:")


def test_apply_migration_no_frontmatter_wraps_minimal() -> None:
    import migrate_add_type as m

    src = "# Just body\n"
    out = m.apply_migration(src, "concept")
    assert out.startswith("---\n")
    assert "type: concept" in out
    assert "# Just body" in out


def test_apply_migration_idempotent() -> None:
    import migrate_add_type as m

    src = '---\ntitle: "X"\ntype: concept\ntags: []\n---\nbody\n'
    out = m.apply_migration(src, "concept")
    assert out == src  # unchanged when already correct
