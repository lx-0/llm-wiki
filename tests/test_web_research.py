"""Tests for `web_research` — dream public-entity enrichment (issue #2).

Covers opt-in detection, the four skip gates (feature flag, per-entity opt-in,
cooldown, API key), the sentinel block render + idempotent upsert, the
air-gap guard (refuse targets outside knowledge/ → nothing in raw/), dry-run,
and fail-soft on a backend error. The live Exa HTTP path is NOT exercised
here (no key); every test injects a fake backend.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

from web_research import (
    SENTINEL_BEGIN,
    SENTINEL_END,
    build_block,
    cooldown_active,
    is_opted_in,
    run_web_research,
    upsert_block,
)

FAKE_RESULTS = [
    {"title": "Brightwave Labs", "url": "https://brightwave.example", "text": "Agency founded by them."},
    {"title": "LinkedIn", "url": "https://linkedin.com/in/x", "text": "CEO & founder."},
]


def _fake_backend(query, api_key, num_results):
    return FAKE_RESULTS


def _config(*, enabled=True, key="exa-key", cooldown=30):
    return SimpleNamespace(
        features=SimpleNamespace(dream_web_research=enabled),
        personal=SimpleNamespace(exa_api_key=key),
        scheduling=SimpleNamespace(web_research_cooldown_days=cooldown),
    )


def _page(tmp_path: Path, fm_lines: list[str], body: str = "# X\n") -> tuple[Path, Path]:
    kd = tmp_path / "knowledge"
    p = kd / "people" / "x.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("---\n" + "\n".join(fm_lines) + "\n---\n\n" + body, encoding="utf-8")
    return p, kd


# ── opt-in ───────────────────────────────────────────────────────────


def test_opt_in_detection():
    assert is_opted_in({"web_research": True})
    assert is_opted_in({"tags": ["public-person"]})
    assert is_opted_in({"tags": "public-person"})
    assert not is_opted_in({"tags": ["founder"]})
    assert not is_opted_in({})


# ── gates ────────────────────────────────────────────────────────────


def test_skip_feature_disabled(tmp_path: Path):
    p, kd = _page(tmp_path, ["type: person", "web_research: true"])
    res = run_web_research(p, config=_config(enabled=False), knowledge_dir=kd, backend=_fake_backend)
    assert res.status == "skipped" and res.reason == "feature_disabled"


def test_skip_not_opted_in(tmp_path: Path):
    p, kd = _page(tmp_path, ["type: person"])
    res = run_web_research(p, config=_config(), knowledge_dir=kd, backend=_fake_backend)
    assert res.status == "skipped" and res.reason == "not_opted_in"


def test_skip_no_api_key(tmp_path: Path):
    p, kd = _page(tmp_path, ["type: person", "web_research: true"])
    res = run_web_research(p, config=_config(key=""), knowledge_dir=kd, backend=_fake_backend)
    assert res.status == "skipped" and res.reason == "no_api_key"


def test_skip_cooldown(tmp_path: Path):
    block = build_block("X", FAKE_RESULTS, today=date(2026, 5, 20))
    p, kd = _page(tmp_path, ["type: person", "web_research: true"], body="# X\n\n" + block + "\n")
    res = run_web_research(
        p, config=_config(cooldown=30), knowledge_dir=kd,
        now=date(2026, 5, 31), backend=_fake_backend,
    )
    assert res.status == "skipped" and res.reason == "cooldown"


def test_cooldown_expired_runs(tmp_path: Path):
    block = build_block("X", FAKE_RESULTS, today=date(2026, 3, 1))
    p, kd = _page(tmp_path, ["type: person", "web_research: true"], body="# X\n\n" + block + "\n")
    res = run_web_research(
        p, config=_config(cooldown=30), knowledge_dir=kd,
        now=date(2026, 5, 31), backend=_fake_backend,
    )
    assert res.status == "ok" and res.wrote


def test_force_bypasses_gates(tmp_path: Path):
    """Standalone `web-research <slug>`: no opt-in, feature off → still runs."""
    p, kd = _page(tmp_path, ["type: person"])
    res = run_web_research(
        p, config=_config(enabled=False), knowledge_dir=kd,
        force=True, backend=_fake_backend,
    )
    assert res.status == "ok" and res.wrote


# ── air-gap ──────────────────────────────────────────────────────────


def test_refuses_target_outside_knowledge(tmp_path: Path):
    kd = tmp_path / "knowledge"
    kd.mkdir()
    raw = tmp_path / "raw" / "notes" / "x.md"
    raw.parent.mkdir(parents=True)
    raw.write_text("---\ntype: person\nweb_research: true\n---\n\n# X\n", encoding="utf-8")
    res = run_web_research(raw, config=_config(), knowledge_dir=kd, force=True, backend=_fake_backend)
    assert res.status == "skipped" and res.reason == "outside_knowledge"
    # And nothing was written into raw/.
    assert SENTINEL_BEGIN not in raw.read_text()


# ── block render + upsert ────────────────────────────────────────────


def test_block_is_sentinel_wrapped_and_dated():
    block = build_block("Sebastian", FAKE_RESULTS, today=date(2026, 5, 31))
    assert block.startswith(SENTINEL_BEGIN) and block.rstrip().endswith(SENTINEL_END)
    assert "## Public Profile" in block
    assert "last updated: 2026-05-31" in block
    assert "[Brightwave Labs](https://brightwave.example)" in block


def test_upsert_idempotent_structure():
    base = "# X\n\nbody\n"
    b1 = build_block("X", FAKE_RESULTS, today=date(2026, 5, 1))
    once = upsert_block(base, b1)
    b2 = build_block("X", FAKE_RESULTS, today=date(2026, 6, 1))
    twice = upsert_block(once, b2)
    assert twice.count(SENTINEL_BEGIN) == 1  # replaced, not stacked
    assert "last updated: 2026-06-01" in twice
    assert "last updated: 2026-05-01" not in twice


def test_upsert_append_bytes_pinned_per_trailing_newline_shape():
    """Byte-compat pin: whatever the page's trailing-newline shape, the append
    seam is exactly one blank line + block + trailing newline. Operator vaults
    carry all three shapes — none may drift."""
    block = f"{SENTINEL_BEGIN}\nB\n{SENTINEL_END}"
    assert upsert_block("# X\n\nbody", block) == f"# X\n\nbody\n\n{block}\n"
    assert upsert_block("# X\n\nbody\n", block) == f"# X\n\nbody\n\n{block}\n"
    assert upsert_block("# X\n\nbody\n\n", block) == f"# X\n\nbody\n\n{block}\n"


def test_upsert_replace_round_trip_is_byte_stable():
    """Re-upserting an identical block is a byte-for-byte fixpoint."""
    block = build_block("X", FAKE_RESULTS, today=date(2026, 5, 1))
    once = upsert_block("# X\n\nbody\n", block)
    assert upsert_block(once, block) == once


def test_upsert_replaces_despite_stray_end_marker():
    """A stray end marker BEFORE the genuine block must not blind the upsert
    (core.markers contract) — the block is replaced in place, never stacked."""
    b1 = build_block("X", FAKE_RESULTS, today=date(2026, 5, 1))
    text = f"# X\n\n{SENTINEL_END}\n\nbody\n\n{b1}\n"
    b2 = build_block("X", FAKE_RESULTS, today=date(2026, 6, 1))
    out = upsert_block(text, b2)
    assert out.count(SENTINEL_BEGIN) == 1
    assert "last updated: 2026-06-01" in out
    assert "last updated: 2026-05-01" not in out


def test_cooldown_stamp_found_despite_stray_end_marker():
    """The cooldown stamp inside the genuine block is still honored when a
    stray end marker precedes it (core.markers contract)."""
    block = build_block("X", FAKE_RESULTS, today=date(2026, 5, 1))
    text = f"# X\n\n{SENTINEL_END}\n\nbody\n\n{block}\n"
    assert cooldown_active(text, cooldown_days=30, now=date(2026, 5, 10))


# ── end-to-end + fail-soft ───────────────────────────────────────────


def test_end_to_end_writes_block_not_raw(tmp_path: Path):
    p, kd = _page(tmp_path, ["type: person", "web_research: true"])
    res = run_web_research(p, config=_config(), knowledge_dir=kd, backend=_fake_backend)
    assert res.status == "ok" and res.wrote
    written = p.read_text()
    assert SENTINEL_BEGIN in written and "Brightwave Labs" in written
    # No raw/ dir was created anywhere.
    assert not (tmp_path / "raw").exists()


def test_dry_run_writes_nothing(tmp_path: Path):
    p, kd = _page(tmp_path, ["type: person", "web_research: true"])
    before = p.read_text()
    res = run_web_research(p, config=_config(), knowledge_dir=kd, dry_run=True, backend=_fake_backend)
    assert res.status == "ok" and not res.wrote and res.block
    assert p.read_text() == before


def test_backend_error_is_failsoft(tmp_path: Path):
    def boom(*_):
        raise ValueError("exa 500")
    p, kd = _page(tmp_path, ["type: person", "web_research: true"])
    res = run_web_research(p, config=_config(), knowledge_dir=kd, backend=boom)
    assert res.status == "failed" and "exa 500" in res.reason
    assert SENTINEL_BEGIN not in p.read_text()  # page untouched


def test_dream_standalone_wiring(tmp_path: Path, monkeypatch, capsys):
    """`wiki dream web-research <slug> --dry-run` glue end-to-end: resolves the
    entity, forces past gates, prints the block. Exercises dream.py wiring,
    not just run_web_research."""
    kd = tmp_path / "knowledge"
    p = kd / "people" / "founder.md"
    p.parent.mkdir(parents=True)
    p.write_text("---\ntype: person\nname: Jordan Hale\n---\n\n# Jordan Hale\n", encoding="utf-8")

    import core.paths as paths
    monkeypatch.setattr(paths, "PEOPLE_DIR", kd / "people", raising=False)
    monkeypatch.setattr(paths, "PROJECTS_DIR", kd / "projects", raising=False)
    monkeypatch.setattr(paths, "AREAS_DIR", kd / "areas", raising=False)
    monkeypatch.setattr(paths, "KNOWLEDGE_DIR", kd, raising=False)
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    import web_research
    monkeypatch.setattr(web_research, "search_exa", _fake_backend)

    import dream
    monkeypatch.setattr(dream, "PEOPLE_DIR", kd / "people", raising=False)
    monkeypatch.setattr(dream, "PROJECTS_DIR", kd / "projects", raising=False)
    monkeypatch.setattr(dream, "AREAS_DIR", kd / "areas", raising=False)
    monkeypatch.setattr(
        dream, "_ENTITY_KINDS",
        {"people": (kd / "people", "person"),
         "projects": (kd / "projects", "project"),
         "areas": (kd / "areas", "area")},
        raising=False,
    )

    ent = dream._resolve_entity("founder")
    assert ent is not None
    rc = dream._run_web_research_standalone(ent, dry_run=True)
    assert rc == 0
    out = capsys.readouterr().out
    assert SENTINEL_BEGIN in out and "Brightwave Labs" in out
    assert SENTINEL_BEGIN not in p.read_text()  # dry-run wrote nothing
