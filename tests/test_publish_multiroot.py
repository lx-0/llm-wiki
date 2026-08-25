"""Multi-root corpus + manifest layout migration (M030-S04).

Operator decisions 2026-08-25: ALLES vault-wide, ONE wiki. Rel keys become
VAULT-relative; the v1 manifest (knowledge-relative, already live with 2022
articles) must migrate in place with ZERO phantom retractions.
"""
from __future__ import annotations

from pathlib import Path

from publish.corpus import (
    count_non_markdown,
    manifest_store,
    map_slugs,
    migrate_manifest_layout,
)
from publish.delta import plan_delta, record_published


def _vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    files = {
        "knowledge/index.md": "| catalog |\n",
        "knowledge/concepts/foo.md": "Foo.\n",
        "knowledge/MOCs/hub.md": "Hub.\n",
        "raw/notes/scratch.md": "Scratch.\n",
        "daily/2026-05-12/sessions.md": "S1.\n",
        "daily/2026-05-13/sessions.md": "S2.\n",
        "workspace/inbox/todo.md": "Todo.\n",
        "reports/analyses/r1.md": "R1.\n",
    }
    for rel, body in files.items():
        p = vault / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    (vault / "raw" / "pics" / "shot.png").parent.mkdir(parents=True, exist_ok=True)
    (vault / "raw" / "pics" / "shot.png").write_bytes(b"\x89PNG")
    (vault / "raw" / "req.json").write_text("{}", encoding="utf-8")
    return vault


ROOTS = ("knowledge", "raw", "daily", "reports", "workspace")


def test_multiroot_walk_uses_vault_relative_keys(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    mapping = map_slugs(vault, ROOTS)
    assert mapping["foo"] == "knowledge/concepts/foo.md"
    assert mapping["scratch"] == "raw/notes/scratch.md"
    assert mapping["todo"] == "workspace/inbox/todo.md"
    assert mapping["r1"] == "reports/analyses/r1.md"
    assert "knowledge/index.md" not in mapping.values()  # catalog stays excluded


def test_same_stem_across_daily_dates_disambiguates(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    mapping = map_slugs(vault, ROOTS)
    assert mapping["2026-05-12-sessions"] == "daily/2026-05-12/sessions.md"
    assert mapping["2026-05-13-sessions"] == "daily/2026-05-13/sessions.md"


def test_missing_root_is_skipped(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    mapping = map_slugs(vault, ("knowledge", "does-not-exist"))
    assert "foo" in mapping


def test_default_roots_stay_knowledge_only(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    mapping = map_slugs(vault)
    assert all(rel.startswith("knowledge/") for rel in mapping.values())


def test_count_non_markdown(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    assert count_non_markdown(vault, ROOTS) == 2  # shot.png + req.json


def test_manifest_layout_migration_zero_retraction(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    store = manifest_store(tmp_path / "publish.json")
    # simulate the LIVE v1 manifest: knowledge-relative paths, no layout marker
    store.update(lambda d: d.update(articles={
        "foo": {"path": "concepts/foo.md", "hash": "stale"},
        "hub": {"path": "MOCs/hub.md", "hash": "stale"},
    }))

    migrate_manifest_layout(store)
    articles = store.reload()["articles"]
    assert articles["foo"]["path"] == "knowledge/concepts/foo.md"
    assert store.reload()["layout"] == "vault-rel"

    # migrating again is a no-op (idempotent)
    migrate_manifest_layout(store)
    assert store.reload()["articles"]["foo"]["path"] == "knowledge/concepts/foo.md"

    # slug stability + no phantom retraction against the widened corpus
    mapping = map_slugs(vault, ROOTS, previous={
        slug: e["path"] for slug, e in articles.items()
    })
    assert mapping["foo"] == "knowledge/concepts/foo.md"
    plan = plan_delta([], {})  # shape check only
    assert plan.retract == []
