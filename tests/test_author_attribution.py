"""Author-attribution feature surface — config knob + migration + yaml example.

Covers the three engine-side surfaces shipped 2026-05-16:

1. `Personal.implicit_operator_author` dataclass field, default `None`.
2. `migrate_config_keys.KEY_ADDITIONS["personal"]` injects the key into
   pre-existing operator vaults under their `personal:` block.
3. `config.example.yaml` documents the key for fresh installs.

Effectiveness of the compile-prompt rule itself is measured on first real
compile pass that hits an `author:`-stamped file (spec: deferred to next
milestone; see `.ytstack/backlog/author-attribution.md`).
"""

from __future__ import annotations

from pathlib import Path

import yaml


def test_personal_dataclass_has_implicit_operator_author_default_none() -> None:
    """`Personal()` instantiates with `implicit_operator_author is None`."""
    from core.config import Personal

    p = Personal()
    assert hasattr(p, "implicit_operator_author"), (
        "Personal dataclass missing implicit_operator_author field"
    )
    assert p.implicit_operator_author is None, (
        f"default should be None, got {p.implicit_operator_author!r}"
    )


def test_personal_dataclass_accepts_string_value() -> None:
    """Setting `implicit_operator_author='alex'` round-trips."""
    from core.config import Personal

    p = Personal(implicit_operator_author="alex")
    assert p.implicit_operator_author == "alex"


def test_key_additions_injects_implicit_operator_author_under_personal(
    tmp_path: Path,
) -> None:
    """A vault config without the key gets it injected under `personal:`."""
    from migrations import migrate_config_keys as m

    # Confirm the migration table has the expected entry.
    assert "personal" in m.KEY_ADDITIONS, (
        "KEY_ADDITIONS missing 'personal' block — migration won't inject"
    )
    assert "implicit_operator_author" in m.KEY_ADDITIONS["personal"], (
        "KEY_ADDITIONS['personal'] missing 'implicit_operator_author'"
    )
    assert m.KEY_ADDITIONS["personal"]["implicit_operator_author"] is None, (
        "default in KEY_ADDITIONS must mirror dataclass default (None)"
    )

    # End-to-end: a vault YAML missing the key should pick it up.
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "personal:\n  primary_account: work\n",
        encoding="utf-8",
    )
    new_text, changes = m.migrate_config(cfg)
    assert new_text is not None, "migration should produce a new YAML body"
    assert any("implicit_operator_author" in c for c in changes), (
        f"no change line mentioned the new key; got: {changes}"
    )
    data = yaml.safe_load(new_text)
    assert data["personal"]["implicit_operator_author"] is None


def test_key_additions_idempotent_when_already_present(tmp_path: Path) -> None:
    """Operator who already set the value (e.g. 'alex') is not overwritten."""
    from migrations import migrate_config_keys as m

    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "personal:\n  primary_account: work\n  implicit_operator_author: alex\n",
        encoding="utf-8",
    )
    new_text, changes = m.migrate_config(cfg)
    # Either no rewrite at all, or the rewrite preserves the operator value.
    if new_text is not None:
        data = yaml.safe_load(new_text)
        assert data["personal"]["implicit_operator_author"] == "alex"
    assert not any(
        "implicit_operator_author" in c and "added" in c for c in changes
    ), f"migration tried to re-inject an already-set key: {changes}"


def test_config_example_yaml_documents_the_key() -> None:
    """`config.example.yaml` carries the key under `personal:` for fresh installs."""
    example = (
        Path(__file__).resolve().parent.parent / "config.example.yaml"
    ).read_text(encoding="utf-8")
    data = yaml.safe_load(example)
    assert "personal" in data, "config.example.yaml missing personal: block"
    assert "implicit_operator_author" in data["personal"], (
        "config.example.yaml missing personal.implicit_operator_author"
    )
    assert data["personal"]["implicit_operator_author"] is None, (
        "example should ship null (multi-tenant-safe default)"
    )
