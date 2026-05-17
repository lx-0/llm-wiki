"""M017 — dream-priority resolution + selection mode tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


# ── Helpers ───────────────────────────────────────────────────────


def _make_entity(tmp_vault: Path, slug: str, kind: str, frontmatter: dict):
    """Drop a fake entity page under tmp_vault/knowledge/<kind>/<slug>.md."""
    page = tmp_vault / "knowledge" / kind / f"{slug}.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    fm_lines = ["---"]
    for k, v in frontmatter.items():
        if isinstance(v, list):
            fm_lines.append(f"{k}: [{', '.join(str(x) for x in v)}]")
        elif isinstance(v, str):
            fm_lines.append(f"{k}: {v}")
        else:
            fm_lines.append(f"{k}: {v}")
    fm_lines.append("---")
    page.write_text("\n".join(fm_lines) + "\n\nbody", encoding="utf-8")
    return page


@pytest.fixture
def vault(tmp_path, monkeypatch):
    """Isolated vault root with patched dream.py + paths globals."""
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    (vault_root / "knowledge" / "people").mkdir(parents=True)
    (vault_root / "knowledge" / "projects").mkdir(parents=True)
    (vault_root / "knowledge" / "areas").mkdir(parents=True)
    monkeypatch.setattr("dream.ROOT_DIR", vault_root)
    monkeypatch.setattr("dream.PEOPLE_DIR", vault_root / "knowledge" / "people")
    monkeypatch.setattr("dream.PROJECTS_DIR", vault_root / "knowledge" / "projects")
    monkeypatch.setattr("dream.AREAS_DIR", vault_root / "knowledge" / "areas")
    monkeypatch.setattr("dream._ENTITY_KINDS", {
        "people": (vault_root / "knowledge" / "people", "person"),
        "projects": (vault_root / "knowledge" / "projects", "project"),
        "areas": (vault_root / "knowledge" / "areas", "area"),
    })
    return vault_root


# ── Layer 1: per-entity frontmatter override ─────────────────────


def test_frontmatter_priority_wins_over_config(vault, monkeypatch):
    """dream_priority in frontmatter beats all config rules."""
    import dream
    _make_entity(vault, "alex", "people", {"dream_priority": 8.5, "domain": "personal"})

    cfg = type("DP", (), {
        "default": 1.0, "paths": {"knowledge/people/alex.md": 99.0},
        "domain": {"personal": 100.0}, "tags": {}, "tag_strategy": "max", "status": {},
    })()
    with patch.object(dream.CONFIG.scheduling, "dream_priority", cfg):
        ent = dream._resolve_entity("alex")
        weight, source = dream.compute_entity_priority(ent)
    assert weight == 8.5
    assert source.startswith("frontmatter:")


def test_frontmatter_zero_excludes(vault, monkeypatch):
    """dream_priority: 0 means excluded, beats config that would weight it."""
    import dream
    _make_entity(vault, "alex", "people", {"dream_priority": 0})
    cfg = type("DP", (), {"default": 5.0, "paths": {}, "domain": {}, "tags": {}, "tag_strategy": "max", "status": {}})()
    with patch.object(dream.CONFIG.scheduling, "dream_priority", cfg):
        ent = dream._resolve_entity("alex")
        weight, _ = dream.compute_entity_priority(ent)
    assert weight == 0.0


# ── Layer 2: path/glob match ─────────────────────────────────────


def test_explicit_path_match(vault, monkeypatch):
    import dream
    _make_entity(vault, "alex", "people", {})
    cfg = type("DP", (), {
        "default": 1.0, "paths": {"knowledge/people/alex.md": 5.0},
        "domain": {}, "tags": {}, "tag_strategy": "max", "status": {},
    })()
    with patch.object(dream.CONFIG.scheduling, "dream_priority", cfg):
        ent = dream._resolve_entity("alex")
        weight, source = dream.compute_entity_priority(ent)
    assert weight == 5.0
    assert "paths:" in source


def test_glob_path_match(vault, monkeypatch):
    import dream
    _make_entity(vault, "personal-old-archived", "areas", {})
    cfg = type("DP", (), {
        "default": 1.0, "paths": {"knowledge/areas/personal-*-archived.md": 0},
        "domain": {}, "tags": {}, "tag_strategy": "max", "status": {},
    })()
    with patch.object(dream.CONFIG.scheduling, "dream_priority", cfg):
        ent = dream._resolve_entity("personal-old-archived")
        weight, _ = dream.compute_entity_priority(ent)
    assert weight == 0.0


def test_paths_first_match_wins(vault, monkeypatch):
    """Earlier path-pattern wins over later more-specific one (operator-controlled order)."""
    import dream
    _make_entity(vault, "alex", "people", {})
    # Dict iteration order = insertion order (Python 3.7+)
    paths = {}
    paths["knowledge/people/*.md"] = 2.0
    paths["knowledge/people/alex.md"] = 5.0  # would win if not first-match
    cfg = type("DP", (), {
        "default": 1.0, "paths": paths,
        "domain": {}, "tags": {}, "tag_strategy": "max", "status": {},
    })()
    with patch.object(dream.CONFIG.scheduling, "dream_priority", cfg):
        ent = dream._resolve_entity("alex")
        weight, _ = dream.compute_entity_priority(ent)
    assert weight == 2.0  # first-match wins


# ── Layer 3: formula multipliers ─────────────────────────────────


def test_domain_multiplier(vault, monkeypatch):
    import dream
    _make_entity(vault, "alex", "people", {"domain": "personal"})
    cfg = type("DP", (), {
        "default": 1.0, "paths": {},
        "domain": {"personal": 1.5}, "tags": {}, "tag_strategy": "max", "status": {},
    })()
    with patch.object(dream.CONFIG.scheduling, "dream_priority", cfg):
        ent = dream._resolve_entity("alex")
        weight, _ = dream.compute_entity_priority(ent)
    assert weight == 1.5  # 1.0 base × 1.5 domain


def test_tag_strategy_max(vault, monkeypatch):
    import dream
    _make_entity(vault, "alex", "people", {"tags": ["work-active", "operator-anchor"]})
    cfg = type("DP", (), {
        "default": 1.0, "paths": {},
        "domain": {}, "tags": {"work-active": 2.5, "operator-anchor": 5.0},
        "tag_strategy": "max", "status": {},
    })()
    with patch.object(dream.CONFIG.scheduling, "dream_priority", cfg):
        ent = dream._resolve_entity("alex")
        weight, _ = dream.compute_entity_priority(ent)
    assert weight == 5.0  # max(2.5, 5.0)


def test_tag_strategy_sum(vault, monkeypatch):
    import dream
    _make_entity(vault, "alex", "people", {"tags": ["work-active", "operator-anchor"]})
    cfg = type("DP", (), {
        "default": 1.0, "paths": {},
        "domain": {}, "tags": {"work-active": 2.5, "operator-anchor": 5.0},
        "tag_strategy": "sum", "status": {},
    })()
    with patch.object(dream.CONFIG.scheduling, "dream_priority", cfg):
        ent = dream._resolve_entity("alex")
        weight, _ = dream.compute_entity_priority(ent)
    assert weight == 7.5  # 2.5 + 5.0


def test_status_multiplier(vault, monkeypatch):
    import dream
    _make_entity(vault, "personal-chng-me", "areas", {"status": "retired"})
    cfg = type("DP", (), {
        "default": 1.0, "paths": {},
        "domain": {}, "tags": {}, "tag_strategy": "max",
        "status": {"active": 1.0, "retired": 0.05},
    })()
    with patch.object(dream.CONFIG.scheduling, "dream_priority", cfg):
        ent = dream._resolve_entity("personal-chng-me")
        weight, _ = dream.compute_entity_priority(ent)
    assert weight == pytest.approx(0.05)


def test_composite_formula(vault, monkeypatch):
    """All multipliers compose: default × domain × tag × status."""
    import dream
    _make_entity(vault, "alex", "people", {
        "domain": "personal", "tags": ["operator-anchor"], "status": "active",
    })
    cfg = type("DP", (), {
        "default": 2.0, "paths": {},
        "domain": {"personal": 1.5},
        "tags": {"operator-anchor": 3.0},
        "tag_strategy": "max",
        "status": {"active": 1.0},
    })()
    with patch.object(dream.CONFIG.scheduling, "dream_priority", cfg):
        ent = dream._resolve_entity("alex")
        weight, _ = dream.compute_entity_priority(ent)
    assert weight == pytest.approx(9.0)  # 2.0 × 1.5 × 3.0 × 1.0


def test_default_when_no_rules_match(vault, monkeypatch):
    import dream
    _make_entity(vault, "obscure", "people", {})
    cfg = type("DP", (), {
        "default": 1.0, "paths": {}, "domain": {}, "tags": {}, "tag_strategy": "max", "status": {},
    })()
    with patch.object(dream.CONFIG.scheduling, "dream_priority", cfg):
        ent = dream._resolve_entity("obscure")
        weight, source = dream.compute_entity_priority(ent)
    assert weight == 1.0
    assert "default:" in source


# ── Selection mode ───────────────────────────────────────────────


def test_select_greedy_top_n():
    import dream
    from dream import EntityRef
    candidates = [
        (1.0, EntityRef(slug="a", kind="people", page=Path("a"), type_value="person"), "src"),
        (5.0, EntityRef(slug="b", kind="people", page=Path("b"), type_value="person"), "src"),
        (3.0, EntityRef(slug="c", kind="people", page=Path("c"), type_value="person"), "src"),
    ]
    picked = dream._select_for_sweep(candidates, N=2, mode="greedy")
    assert len(picked) == 2
    assert picked[0][1].slug == "b"
    assert picked[1][1].slug == "c"


def test_select_zero_weight_excluded():
    import dream
    from dream import EntityRef
    candidates = [
        (0.0, EntityRef(slug="zero", kind="people", page=Path("z"), type_value="person"), "excluded"),
        (1.0, EntityRef(slug="one", kind="people", page=Path("o"), type_value="person"), "src"),
    ]
    picked = dream._select_for_sweep(candidates, N=5, mode="greedy")
    assert len(picked) == 1
    assert picked[0][1].slug == "one"


def test_select_probabilistic_returns_n_items():
    """Probabilistic mode returns exactly min(N, eligible_count) without replacement."""
    import dream
    from dream import EntityRef
    candidates = [
        (float(i + 1), EntityRef(slug=f"e{i}", kind="people", page=Path(str(i)), type_value="person"), "src")
        for i in range(5)
    ]
    picked = dream._select_for_sweep(candidates, N=3, mode="probabilistic")
    assert len(picked) == 3
    # No duplicates
    slugs = [p[1].slug for p in picked]
    assert len(slugs) == len(set(slugs))


def test_select_probabilistic_biased_toward_high_weight():
    """Over many rolls, high-weight entity selected more often than low-weight."""
    import dream
    from dream import EntityRef
    candidates = [
        (10.0, EntityRef(slug="high", kind="people", page=Path("h"), type_value="person"), "src"),
        (1.0, EntityRef(slug="low", kind="people", page=Path("l"), type_value="person"), "src"),
    ]
    high_count = 0
    for _ in range(200):
        picked = dream._select_for_sweep(candidates, N=1, mode="probabilistic")
        if picked and picked[0][1].slug == "high":
            high_count += 1
    # 10:1 weight ratio → high should win ~90% of the time; allow loose bound
    assert high_count > 150, f"expected ≥150 high-picks, got {high_count}"


# ── list_candidates output ───────────────────────────────────────


def test_list_candidates_shape(vault, monkeypatch):
    import dream
    _make_entity(vault, "alex", "people", {"domain": "personal"})
    _make_entity(vault, "yesterday-os", "projects", {"domain": "ai"})
    cfg = type("DP", (), {
        "default": 1.0, "paths": {"knowledge/people/alex.md": 5.0},
        "domain": {"ai": 1.5}, "tags": {}, "tag_strategy": "max", "status": {},
    })()
    with patch.object(dream.CONFIG.scheduling, "dream_priority", cfg):
        rows = dream.list_candidates()
    assert len(rows) == 2
    by_slug = {r["slug"]: r for r in rows}
    assert by_slug["alex"]["priority"] == 5.0
    assert by_slug["yesterday-os"]["priority"] == 1.5
    # alex has higher weight × age → ranked first
    assert rows[0]["slug"] == "alex"
