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

NOW = datetime(2026, 8, 26, 12, 0, 0).astimezone()


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


@pytest.fixture
def piggy_config(monkeypatch):
    """One enabled 6h-cooldown task; stale factor 4 → stale after 24h.

    Patches the SCHEDULER's task list (the same source `flush.py` fires from),
    not CONFIG.piggybacks — the state file is keyed by scheduler task name,
    which is NOT the config key for built-in tasks (`review_wiki` persists as
    `review-wiki`).
    """
    from core.config import CONFIG

    monkeypatch.setattr(health, "_piggyback_tasks", lambda: [
        {"name": "gmeet", "cooldown_hours": 6},
    ])
    monkeypatch.setattr(CONFIG.limits, "doctor_piggyback_stale_factor", 4)
    monkeypatch.setattr(CONFIG.limits, "doctor_piggyback_stale_min_hours", 24)
    return CONFIG


def test_state_key_matches_scheduler_not_config_key(tmp_path, monkeypatch):
    """Regression (live-found 2026-08-26): the check iterated CONFIG.piggybacks
    and looked those names up in piggyback-state.json, but built-in tasks
    persist under `name.replace('_','-')` — so 12 healthy tasks on the live
    vault were reported 'never ran'. The scheduler's own task list is the
    single source of truth for both the key and the cooldown."""
    from core.config import CONFIG

    monkeypatch.setattr(health, "_piggyback_tasks", lambda: [
        {"name": "review-wiki", "cooldown_hours": 168},
    ])
    monkeypatch.setattr(CONFIG.limits, "doctor_piggyback_stale_factor", 4)
    monkeypatch.setattr(CONFIG.limits, "doctor_piggyback_stale_min_hours", 24)
    sf = _state_file(tmp_path, {"review-wiki": {
        "status": "ok", "last_run": _iso(NOW - timedelta(hours=2)),
    }})
    results = health.check_piggyback_health(state_file=sf, now=NOW)
    assert [r.severity for r in results] == ["ok"]


def test_short_cadence_not_stale_within_min_hours(tmp_path, monkeypatch):
    """Live false positive: `voice` (1h cadence) warned 'substrate dark' after
    12h. Piggybacks only fire when the operator compiles, so factor×cooldown
    alone flags every short-cadence task during any normal quiet stretch. The
    threshold floors at doctor_piggyback_stale_min_hours."""
    from core.config import CONFIG

    monkeypatch.setattr(health, "_piggyback_tasks", lambda: [
        {"name": "voice", "cooldown_hours": 1},
    ])
    monkeypatch.setattr(CONFIG.limits, "doctor_piggyback_stale_factor", 4)
    monkeypatch.setattr(CONFIG.limits, "doctor_piggyback_stale_min_hours", 24)
    sf = _state_file(tmp_path, {"voice": {
        "status": "ok", "last_run": _iso(NOW - timedelta(hours=12)),
    }})
    assert [r.severity for r in health.check_piggyback_health(state_file=sf, now=NOW)] == ["ok"]

    # Past the floor it does warn — the check still has teeth.
    sf2 = _state_file(tmp_path, {"voice": {
        "status": "ok", "last_run": _iso(NOW - timedelta(hours=30)),
    }})
    assert any(r.severity == "warning"
               for r in health.check_piggyback_health(state_file=sf2, now=NOW))


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


def test_disabled_task_ignored(tmp_path, piggy_config):
    """A disabled task with a rotten status must not warn — the scheduler's
    task list already excludes disabled tasks, so a stale state entry for one
    is simply not looked at."""
    sf = _state_file(tmp_path, {
        "gmeet": {"status": "ok", "last_run": _iso(NOW - timedelta(hours=2))},
        "optimize-claude-md": {"status": "failed:7",
                               "last_run": _iso(NOW - timedelta(days=30))},
    })
    results = health.check_piggyback_health(state_file=sf, now=NOW)
    assert [r.severity for r in results] == ["ok"]


def test_idle_pipeline_collapses_into_one_warning(tmp_path, monkeypatch):
    """Live 2026-08-27: the operator had not compiled for 1.7 days, and doctor
    printed EIGHT 'substrate dark' warnings — one per task, all describing the
    same single fact. A banner where most lines repeat one root cause trains
    the reader to skim past it. Piggybacks fire from compile/flush, so when
    they are all stale together the finding is 'the pipeline is idle', once."""
    from core.config import CONFIG

    monkeypatch.setattr(health, "_piggyback_tasks", lambda: [
        {"name": n, "cooldown_hours": 6} for n in ("calendar", "gmeet", "jamie", "voice")
    ])
    monkeypatch.setattr(CONFIG.limits, "doctor_piggyback_stale_factor", 4)
    monkeypatch.setattr(CONFIG.limits, "doctor_piggyback_stale_min_hours", 24)

    last = _iso(NOW - timedelta(days=1, hours=17))
    sf = _state_file(tmp_path, {
        n: {"status": "ok", "last_run": last} for n in ("calendar", "gmeet", "jamie", "voice")
    })
    results = health.check_piggyback_health(state_file=sf, now=NOW)
    warns = [r for r in results if r.severity == "warning"]
    assert len(warns) == 1, [r.message for r in warns]
    assert "pipeline" in warns[0].message.lower()
    assert "4" in warns[0].message  # names how many tasks it covers


def test_one_task_dark_while_the_pipeline_runs_still_warns_individually(tmp_path, monkeypatch):
    """The signal that must NOT be collapsed: everything else fired recently,
    so this task is genuinely broken rather than merely un-triggered."""
    from core.config import CONFIG

    monkeypatch.setattr(health, "_piggyback_tasks", lambda: [
        {"name": n, "cooldown_hours": 6} for n in ("calendar", "gmeet", "jamie")
    ])
    monkeypatch.setattr(CONFIG.limits, "doctor_piggyback_stale_factor", 4)
    monkeypatch.setattr(CONFIG.limits, "doctor_piggyback_stale_min_hours", 24)

    sf = _state_file(tmp_path, {
        "calendar": {"status": "ok", "last_run": _iso(NOW - timedelta(hours=2))},
        "jamie": {"status": "ok", "last_run": _iso(NOW - timedelta(hours=3))},
        "gmeet": {"status": "ok", "last_run": _iso(NOW - timedelta(days=21))},
    })
    results = health.check_piggyback_health(state_file=sf, now=NOW)
    warns = [r for r in results if r.severity == "warning"]
    assert len(warns) == 1
    assert "gmeet" in warns[0].message
    assert "pipeline" not in warns[0].message.lower()


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
