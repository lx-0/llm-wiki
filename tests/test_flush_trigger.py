"""flush.maybe_trigger_compile — the ingested-ledger skip branch.

RED-GREEN regression for a verified dead branch (StateStore arc): the old
hand-rolled ledger read keyed by DAILY_DIR-relative path while compile.py
writes ROOT_DIR-relative keys, AND called ``.get("hash")`` on values that are
plain 16-hex strings — double schema drift, so the "Skipping compile —
unchanged" branch could never fire and every evening flush unconditionally
spawned compile. The contract under test: flush consumes the ingested-ledger
API (``core.state_store.is_ingested``) instead of re-implementing the schema.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from core.utils import file_hash  # noqa: E402


@pytest.fixture
def vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """tmp vault with a daily rollup file + state.json redirected for both
    flush and the ingested-ledger API. Returns (vault_root, daily_file, spawns)."""
    import flush
    from core import state_store

    daily = tmp_path / "daily" / "2026-07-18"
    daily.mkdir(parents=True)
    daily_file = daily / "sessions.md"
    daily_file.write_text("## Session\n\n- did things\n", encoding="utf-8")

    state_dir = tmp_path / ".wiki" / "state"
    state_dir.mkdir(parents=True)

    # Old code path reads flush.STATE_DIR/state.json; new code path reads the
    # ledger API (state_store.STATE_FILE + ROOT_DIR). Redirect both so the test
    # pins the CONTRACT, not the implementation.
    monkeypatch.setattr(flush, "STATE_DIR", state_dir, raising=True)
    monkeypatch.setattr(flush, "DAILY_DIR", tmp_path / "daily", raising=True)
    monkeypatch.setattr(flush, "ROOT_DIR", tmp_path, raising=True)
    monkeypatch.setattr(state_store, "STATE_FILE", state_dir / "state.json", raising=True)
    monkeypatch.setattr(state_store, "ROOT_DIR", tmp_path, raising=True)

    # Bypass the evening gate deterministically.
    monkeypatch.setattr(flush, "COMPILE_AFTER_HOUR", 0, raising=True)

    spawns: list[list[str]] = []

    class _FakeProc:
        pid = 4242

    def _fake_popen(cmd, **kwargs):  # noqa: ARG001
        spawns.append(list(cmd))
        return _FakeProc()

    monkeypatch.setattr(flush.subprocess, "Popen", _fake_popen)
    return tmp_path, daily_file, spawns


def _seed_ledger(vault_root: Path, daily_file: Path) -> None:
    """Write state.json exactly the way compile.py does: ROOT_DIR-relative key,
    plain 16-hex hash string value."""
    rel = str(daily_file.relative_to(vault_root))
    state = {"ingested": {rel: file_hash(daily_file)}, "total_cost": 0.0}
    state_file = vault_root / ".wiki" / "state" / "state.json"
    state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")


def test_unchanged_daily_file_skips_compile(vault):
    """A daily file whose content hash matches the ledger must NOT respawn
    compile — the whole point of the skip branch."""
    import flush

    vault_root, daily_file, spawns = vault
    _seed_ledger(vault_root, daily_file)

    flush.maybe_trigger_compile(daily_file)

    assert spawns == [], (
        "compile spawned despite unchanged ledger hash — the skip branch is dead "
        "(schema drift: DAILY_DIR-relative key / dict-value read)"
    )


def test_changed_daily_file_triggers_compile(vault):
    """Content drift after the last compile must still spawn compile."""
    import flush

    vault_root, daily_file, spawns = vault
    _seed_ledger(vault_root, daily_file)
    daily_file.write_text("## Session\n\n- did MORE things\n", encoding="utf-8")

    flush.maybe_trigger_compile(daily_file)

    assert len(spawns) == 1
    assert str(daily_file) in spawns[0]


def test_never_ingested_daily_file_triggers_compile(vault):
    """No ledger entry at all → compile runs (first flush of the day)."""
    import flush

    _vault_root, daily_file, spawns = vault
    flush.maybe_trigger_compile(daily_file)
    assert len(spawns) == 1


def test_corrupt_state_json_fails_open(vault):
    """A corrupt state.json must not crash flush — compile is spawned and
    re-checks the ledger itself."""
    import flush

    vault_root, daily_file, spawns = vault
    (vault_root / ".wiki" / "state" / "state.json").write_text("{not json", encoding="utf-8")

    flush.maybe_trigger_compile(daily_file)
    assert len(spawns) == 1


def test_hour_gate_still_blocks(vault, monkeypatch: pytest.MonkeyPatch):
    """Before COMPILE_AFTER_HOUR nothing is spawned, ledger or not."""
    import flush

    _vault_root, daily_file, spawns = vault
    monkeypatch.setattr(flush, "COMPILE_AFTER_HOUR", 25, raising=True)

    flush.maybe_trigger_compile(daily_file)
    assert spawns == []
