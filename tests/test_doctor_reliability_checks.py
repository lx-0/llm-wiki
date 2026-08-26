"""Doctor reliability checks (M031-S04): piggyback health/freshness + index drift.

The 2026-08-25 audit found silent failure classes doctor never surfaced: a
piggyback stuck on a stale failed status for a day (E5's surface), substrates
dark for weeks with nothing flagging it, and knowledge/index.md drifting from
the corpus. These checks make each visible on `wiki doctor`.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

import core.health as health
from core.config_schema import PiggybackTask

NOW = datetime(2026, 8, 26, 12, 0, 0).astimezone()


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


@pytest.fixture
def piggy_config(monkeypatch):
    """One enabled 6h-cooldown task; stale factor 4 → stale after 24h."""
    from core.config import CONFIG

    monkeypatch.setattr(CONFIG, "piggybacks", {
        "gmeet": PiggybackTask(enabled=True, cooldown_hours=6),
        "off_task": PiggybackTask(enabled=False, cooldown_hours=1),
    })
    monkeypatch.setattr(CONFIG.limits, "doctor_piggyback_stale_factor", 4)
    return CONFIG


def _state_file(tmp_path: Path, data: dict) -> Path:
    sf = tmp_path / "piggyback-state.json"
    sf.write_text(json.dumps(data), encoding="utf-8")
    return sf


def test_piggyback_failed_status_warns(tmp_path, piggy_config):
    sf = _state_file(tmp_path, {"gmeet": {
        "status": "failed:1", "last_error": "exit 1",
        "last_run": _iso(NOW - timedelta(hours=1)),
    }})
    results = health.check_piggyback_health(state_file=sf, now=NOW)
    warn = [r for r in results if r.severity == "warning"]
    assert len(warn) == 1
    assert "gmeet" in warn[0].message and "exit 1" in warn[0].message


def test_piggyback_hung_running_warns(tmp_path, piggy_config):
    """status=running past the runner's wall-clock cap = orphaned/hung runner
    (the runner itself would have recorded timeout at the cap)."""
    sf = _state_file(tmp_path, {"gmeet": {
        "status": "running",
        "started": _iso(NOW - timedelta(hours=6)),
        "last_run": _iso(NOW - timedelta(hours=6)),
    }})
    results = health.check_piggyback_health(state_file=sf, now=NOW)
    warn = [r for r in results if r.severity == "warning"]
    assert len(warn) == 1 and "gmeet" in warn[0].message


def test_piggyback_stale_last_run_warns(tmp_path, piggy_config):
    """Substrate freshness: ok status but no fire for 10 days on a 6h cadence
    (factor 4 → threshold 24h) = collector dark."""
    sf = _state_file(tmp_path, {"gmeet": {
        "status": "ok", "last_error": None,
        "last_run": _iso(NOW - timedelta(days=10)),
    }})
    results = health.check_piggyback_health(state_file=sf, now=NOW)
    warn = [r for r in results if r.severity == "warning"]
    assert len(warn) == 1 and "gmeet" in warn[0].message


def test_piggyback_healthy_is_single_ok(tmp_path, piggy_config):
    sf = _state_file(tmp_path, {"gmeet": {
        "status": "ok", "last_error": None,
        "last_run": _iso(NOW - timedelta(hours=2)),
    }})
    results = health.check_piggyback_health(state_file=sf, now=NOW)
    assert [r.severity for r in results] == ["ok"]


def test_piggyback_disabled_task_ignored(tmp_path, piggy_config):
    """A disabled task with a rotten status must not warn."""
    sf = _state_file(tmp_path, {
        "gmeet": {"status": "ok", "last_run": _iso(NOW - timedelta(hours=2))},
        "off_task": {"status": "failed:7", "last_run": _iso(NOW - timedelta(days=30))},
    })
    results = health.check_piggyback_health(state_file=sf, now=NOW)
    assert [r.severity for r in results] == ["ok"]


def test_piggyback_never_ran_is_info(tmp_path, piggy_config):
    sf = _state_file(tmp_path, {})
    results = health.check_piggyback_health(state_file=sf, now=NOW)
    assert [r.severity for r in results] == ["info"]
    assert "gmeet" in results[0].message


def test_index_drift_quick_skips(tmp_path):
    r = health.check_index_drift(quick=True, knowledge_dir=tmp_path, vault=tmp_path.parent)
    assert r.severity == "info"


def _seed_vault(tmp_path: Path) -> tuple[Path, Path]:
    vault = tmp_path / "vault"
    knowledge = vault / "knowledge"
    (knowledge / "concepts").mkdir(parents=True)
    (knowledge / "concepts" / "foo.md").write_text(
        "# Foo\n\nA real article body.\n", encoding="utf-8"
    )
    return knowledge, vault


def test_index_drift_warns_with_reindex_fix(tmp_path):
    knowledge, vault = _seed_vault(tmp_path)
    (knowledge / "index.md").write_text(
        "# Index\n\n| Article | Summary |\n| --- | --- |\n"
        "| [[concepts/gone]] | dangling row |\n",
        encoding="utf-8",
    )
    r = health.check_index_drift(knowledge_dir=knowledge, vault=vault)
    assert r.severity == "warning"
    assert r.dispatch_args == ["reindex"]


def test_index_drift_ok_when_reconciled(tmp_path):
    from core.index_sync import sync_index

    knowledge, vault = _seed_vault(tmp_path)
    (knowledge / "index.md").write_text(
        "# Index\n\n| Article | Summary |\n| --- | --- |\n",
        encoding="utf-8",
    )
    sync_index(knowledge, vault, today="2026-08-26", apply=True)
    r = health.check_index_drift(knowledge_dir=knowledge, vault=vault)
    assert r.severity == "ok"
