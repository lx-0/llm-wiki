"""Tests for scripts/core/piggybacks.py — the piggyback scheduling core.

Extracted from flush.py so `compile.py` can drain due maintenance at the end
of the operator's actual loop (`wiki compile`) without importing flush.py (which
pulls the Claude SDK and mutates `CLAUDE_INVOKED_BY` at module load).

The scheduling DECISION (`due_tasks`) is a pure function so it's testable with
no subprocess/mock: given the persisted cooldown state + a wall-clock `now`, it
returns exactly the tasks that should fire. The spawn side is a thin wrapper.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from core import piggybacks

UTC = ZoneInfo("UTC")

_TASKS = [
    {"name": "dream-cycle", "cmd": ["dream.py", "piggyback"], "cooldown_hours": 24},
    {"name": "lint-structural", "cmd": ["lint.py"], "cooldown_hours": 24},
]


def test_due_tasks_respects_hour_gate_by_default():
    """Before `after_hour`, the default (flush) path fires nothing — preserving
    the evening-only piggyback behavior."""
    now = datetime(2026, 6, 13, 14, 0, tzinfo=UTC)  # 14:00, before the 18:00 gate
    due = piggybacks.due_tasks(
        state={}, now=now, tasks=_TASKS, after_hour=18, ignore_hour_gate=False
    )
    assert due == []


def test_due_tasks_ignores_hour_gate_when_requested():
    """The compile path bypasses the hour gate: the operator works daytime, so
    maintenance must drain whenever they compile, gated only by cooldown."""
    now = datetime(2026, 6, 13, 14, 0, tzinfo=UTC)  # same pre-gate hour
    due = piggybacks.due_tasks(
        state={}, now=now, tasks=_TASKS, after_hour=18, ignore_hour_gate=True
    )
    assert [t["name"] for t in due] == ["dream-cycle", "lint-structural"]


def test_due_tasks_excludes_tasks_inside_cooldown():
    """A task whose last_run is newer than its cooldown is skipped; an elapsed
    one fires."""
    now = datetime(2026, 6, 13, 20, 0, tzinfo=UTC)  # after the gate
    state = {
        "dream-cycle": {"last_run": (now - timedelta(hours=1)).isoformat()},   # within 24h
        "lint-structural": {"last_run": (now - timedelta(hours=25)).isoformat()},  # elapsed
    }
    due = piggybacks.due_tasks(
        state=state, now=now, tasks=_TASKS, after_hour=18, ignore_hour_gate=False
    )
    assert [t["name"] for t in due] == ["lint-structural"]


def test_due_tasks_corrupt_timestamp_runs_anyway():
    """A garbage last_run must not strand a task forever — it fires."""
    now = datetime(2026, 6, 13, 20, 0, tzinfo=UTC)
    state = {"dream-cycle": {"last_run": "not-a-timestamp"}}
    due = piggybacks.due_tasks(
        state=state, now=now, tasks=[_TASKS[0]], after_hour=18, ignore_hour_gate=False
    )
    assert [t["name"] for t in due] == ["dream-cycle"]


def test_run_due_piggybacks_spawns_due_task_wrapped_in_runner(monkeypatch):
    """End-to-end of the spawn path with ONLY the OS-spawn + state-write
    boundaries stubbed: a due task (hour-gate bypassed) is launched via the
    piggyback_runner wrapper with the real resolved script path. `lint.py` is a
    real script under scripts/ so the existence check passes; Popen never
    actually runs it."""
    import core.piggyback_runner as runner_mod

    popen_calls: list[list[str]] = []
    recorded: list[tuple[str, dict]] = []
    monkeypatch.setattr(piggybacks.subprocess, "Popen", lambda cmd, **kw: popen_calls.append(cmd))
    monkeypatch.setattr(runner_mod, "record_status", lambda name, payload: recorded.append((name, payload)))
    monkeypatch.setattr(
        piggybacks, "build_piggyback_tasks",
        lambda: [{"name": "lint-structural", "cmd": ["lint.py", "--structural-only"], "cooldown_hours": 24}],
    )
    monkeypatch.setattr(piggybacks, "load_piggyback_state", lambda: {})

    spawned = piggybacks.run_due_piggybacks(ignore_hour_gate=True)

    assert spawned == ["lint-structural"]
    assert len(popen_calls) == 1
    flat = " ".join(popen_calls[0])
    assert "piggyback_runner.py" in flat                       # wrapped under the wall-clock cap
    assert str(piggybacks.SCRIPTS_DIR / "lint.py") in flat     # real resolved script path
    assert "--structural-only" in flat
    assert recorded and recorded[0][0] == "lint-structural"    # cooldown ledger stamped
