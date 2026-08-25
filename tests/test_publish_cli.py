"""Tests for `wiki publish --dry-run` (M030-S01-T05)."""
from __future__ import annotations

from pathlib import Path

from publish.cli import build_publish_plan, render_human, to_json_payload
from publish.corpus import manifest_store
from publish.delta import record_published


def _vault(tmp_path: Path) -> tuple[Path, Path]:
    vault = tmp_path / "vault"
    k = vault / "knowledge"
    for rel, body in {
        "concepts/foo.md": "Foo body.\n",
        "people/bar.md": "Bar body.\n",
    }.items():
        p = k / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    (k / "index.md").write_text(
        "| Article | Summary | Compiled From | Updated |\n"
        "|---------|---------|---------------|---------|\n"
        "| [[concepts/foo]] | About foo. | raw/a.md | 2026-08-01 |\n",
        encoding="utf-8",
    )
    return vault, k


def test_dry_run_plan_golden(tmp_path: Path) -> None:
    vault, k = _vault(tmp_path)
    store = manifest_store(tmp_path / "publish.json")
    plan, slug_map = build_publish_plan(k, vault, store)
    assert to_json_payload(plan) == {
        "create": [
            {"slug": "bar", "path": "people/bar.md"},
            {"slug": "foo", "path": "concepts/foo.md"},
        ],
        "update": [],
        "retract": [],
        "unchanged": 0,
    }
    assert slug_map == {"bar": "people/bar.md", "foo": "concepts/foo.md"}


def test_dry_run_is_idempotent_after_publish(tmp_path: Path) -> None:
    vault, k = _vault(tmp_path)
    store = manifest_store(tmp_path / "publish.json")
    plan, _ = build_publish_plan(k, vault, store)
    for payload in plan.create:
        record_published(store, payload)
    second, _ = build_publish_plan(k, vault, store)
    assert to_json_payload(second) == {
        "create": [], "update": [], "retract": [], "unchanged": 2,
    }


def test_render_human_shows_totals(tmp_path: Path) -> None:
    vault, k = _vault(tmp_path)
    store = manifest_store(tmp_path / "publish.json")
    plan, _ = build_publish_plan(k, vault, store)
    out = render_human(plan)
    assert "2 create" in out and "0 unchanged" in out
    assert "foo" in out and "people/bar.md" in out


def test_command_catalog_has_publish_row() -> None:
    import cli

    row = next(c for c in cli.COMMANDS if c.name == "publish")
    assert row.handler == "publish/cli.py"
    assert row.kind == "py"
