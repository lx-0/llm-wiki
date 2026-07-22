"""M026-S02-T02: characterization tests for compile_file's dispatch.

Written against the LEGACY compile_file (must pass before the decide_route
wiring), then re-run after the refactor to prove behavior is identical. The
SDK call is faked; ROOT_DIR + state are redirected to a tmp vault.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest


@pytest.fixture
def vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """tmp vault with ROOT_DIR redirected in compile + route, state captured."""
    import compile as cmod
    from compile_stages import route as rmod

    raw = tmp_path / "raw" / "notes"
    raw.mkdir(parents=True)
    (tmp_path / "knowledge").mkdir()
    (tmp_path / "knowledge" / "index.md").write_text("# Index\n", encoding="utf-8")

    monkeypatch.setattr(cmod, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(cmod, "INDEX_FILE", tmp_path / "knowledge" / "index.md")
    monkeypatch.setattr(rmod, "ROOT_DIR", tmp_path)

    saved: dict = {}
    monkeypatch.setattr(cmod, "load_state", lambda: {k: dict(v) if isinstance(v, dict) else v for k, v in saved.items()})

    # State writes go through the merge-under-lock seam now (StateStore arc);
    # capture them so no test touches the real state.json.
    def _fake_update_state(mutator):
        mutator(saved)
        return saved

    monkeypatch.setattr(cmod, "update_state", _fake_update_state)
    monkeypatch.setattr(cmod, "file_hash", lambda p: "HASH")

    return tmp_path, raw, saved


def _run(source: Path):
    import compile as cmod

    return asyncio.run(cmod.compile_file(source))


def test_empty_file_skips(vault):
    _, raw, _ = vault
    src = raw / "empty.md"
    src.write_text("   \n", encoding="utf-8")
    o = _run(src)
    # Deterministic skips record the ingested-hash so they drop out of the
    # candidate list (until the body changes), instead of re-listing forever.
    assert o.status == "skipped" and o.skip_reason == "empty" and o.ingest_hash is True


def test_final_only_skips(vault):
    _, raw, _ = vault
    src = raw / "curated.md"
    src.write_text("---\ncompile_role: final-only\n---\nhand-curated", encoding="utf-8")
    o = _run(src)
    assert o.status == "skipped" and o.skip_reason == "compile_role_final_only"
    assert o.ingest_hash is True


def test_substrate_excluded_skip_records_hash(vault, monkeypatch):
    """email-delta (and any compile_skip_substrate_types member) must record its
    ingested-hash on skip — otherwise the collector's write-once delta files
    re-list as compile candidates on every run forever (lxw, 2026-06-02)."""
    from core.config import CONFIG
    monkeypatch.setattr(
        CONFIG.limits, "compile_skip_substrate_types", ("email-delta",)
    )
    _, raw, _ = vault
    src = raw / "delta-2026-06-02.md"
    src.write_text("---\ntype: email-delta\n---\n- new mail summary", encoding="utf-8")
    o = _run(src)
    assert o.status == "skipped"
    assert o.skip_reason == "substrate_type_excluded_email-delta"
    assert o.ingest_hash is True


def test_health_rollup_stub_records_deterministically(vault):
    _, raw, saved = vault
    src = raw / "health.md"
    src.write_text(
        "---\ntype: health-rollup\n---\n# Health — 2026-05-20\n"
        "(Add observations below as needed.)",
        encoding="utf-8",
    )
    o = _run(src)
    assert o.status == "skipped" and o.skip_reason == "health_rollup_stub_deterministic"
    # handler signals ingest_hash; main() (not compile_file) persists -> saved empty
    assert o.ingest_hash is True
    assert saved == {}


def test_plain_note_routes_to_compile_source(vault, monkeypatch):
    _, raw, _ = vault
    from compile_stages import compile as cs_mod
    from compile_stages.types import CompileResult

    seen = {}

    async def fake_compile_source(content, metadata):
        seen["content"] = content
        seen["substrate_prompt"] = metadata.substrate_prompt
        seen["model_id"] = metadata.model_id
        return CompileResult(
            status="ok", article="A", cost_usd=0.5, input_tokens=3, output_tokens=2
        )

    monkeypatch.setattr(cs_mod, "compile_source", fake_compile_source)

    src = raw / "note.md"
    src.write_text("---\ntype: random-unmapped\n---\njust a note", encoding="utf-8")
    outcome = _run(src)

    assert outcome.status == "compiled"
    assert outcome.cost_usd == 0.5
    assert outcome.input_tokens == 3
    assert outcome.article == "A"
    assert outcome.ingest_hash is True
    assert seen["substrate_prompt"] == "compile_default"
    assert seen["content"] == "---\ntype: random-unmapped\n---\njust a note"
