"""Piggyback scheduling core — task table, cooldown gate, detached spawn.

Extracted from `flush.py` so `compile.py` can drain due maintenance at the end
of the operator's real loop (`wiki compile`) WITHOUT importing flush.py: flush
pulls the Claude SDK and sets `CLAUDE_INVOKED_BY` at module load, neither of
which a compile process should inherit.

Why the split matters for the operator: the piggybacks (dream-cycle, lint,
curiosity-drain, daily-digest, …) only ever fired from `flush.py` after
`scheduling.compile_after_hour`. An operator who lives in `wiki update && wiki
compile` and rarely flushes during the day never triggered them, so every
maintenance queue piled up and the home screen nagged about each one manually.
`run_due_piggybacks(ignore_hour_gate=True)` from compile fixes that: the queues
drain inside the workflow the operator already runs.

`due_tasks` is a PURE function (state + now in, task list out) so the scheduling
decision is unit-testable with no subprocess or mock.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from core.config import CONFIG

SCRIPTS_DIR = Path(__file__).resolve().parent.parent  # core/ → scripts/
WIKI_DIR = SCRIPTS_DIR.parent
STATE_DIR = WIKI_DIR / "state"
PIGGYBACK_STATE_FILE = STATE_DIR / "piggyback-state.json"

_module_log = logging.getLogger(__name__)


# Piggyback tasks — two DISCOVERY paths, one defaults source:
#
# 1. Registry-discovered Collectors with `SPEC.piggyback_default=True` —
#    spawned as `collectors/cli.py <name>` (the canonical CLI for collectors).
# 2. Built-in non-Collector tasks — maintenance / synthesis commands listed
#    explicitly below. These are NOT "legacy not yet ported": lint, review,
#    daily-digest, dream-cycle, study/analyst, reconcile, health-trends are
#    deliberately not Collectors (they read the vault, not a substrate).
#
# enabled / cooldown_hours / max_per_run come from CONFIG.piggybacks.<name>
# for both paths; the defaults behind that live in ONE place —
# `core.config_schema._default_piggybacks` (parity with each collector's
# SPEC.piggyback_cooldown_hours is enforced by
# tests/test_piggyback_defaults.py).

_BUILTIN_PIGGYBACK_TASKS: dict[str, list[str]] = {
    "lint_structural": ["lint.py", "--structural-only"],
    "review_wiki": ["review-wiki.py"],
    "optimize_claude_md": ["optimize-claude-md.py"],
    "retry_failed_flushes": ["retry-failed-flushes.py", "--limit", "{max_per_run}"],
    # Drain N oldest requests per fire (configurable via max_per_run).
    # Steady-rate beats --run-oldest (1/fire) for keeping ahead of the
    # producer when compile runs on many sources at once.
    "curiosity_followup": ["curiosity/cli.py", "--run-batch", "{max_per_run}"],
    # Distills yesterday's per-source captures under daily/<yesterday>/ into
    # a tight ≤500-word digest at daily/<yesterday>.md. Runs morning-after so
    # all collector piggybacks have already landed their per-source files.
    "daily_digest_yesterday": ["daily_digest_runner.py", "--date", "yesterday"],
    # M014 dream-cycle. Sweeps the N most-overdue entity pages (oldest
    # last_synthesized_at first) and resynthesizes their State + Timeline
    # from the full substrate corpus. Per-run cost cap is enforced inside
    # dream.py via limits.dream_cycle_max_tokens_per_run; this template
    # just hands over max_per_run as the entity-count ceiling.
    "dream_cycle": ["dream.py", "piggyback", "--limit", "{max_per_run}"],
    # M019 operator-self-reports surface. Fires N hours per cooldown,
    # walks `<vault>/<personal.reports_dir>/studies/*/`, runs each study
    # whose schedule (weekly / monthly / quarterly) says it's due. Each
    # study takes its own per-study flock so concurrent piggyback fires
    # don't double-score and cross-study runs proceed in parallel. The
    # cooldown here gates how often we CHECK for due studies; the
    # study's own schedule gates when it actually runs.
    "study_run_due": ["study.py", "piggyback"],
    # M019-S05 Pass-2 analyst — cross-study synthesis. Reads all
    # latest Pass-1 outputs + their _summary.md siblings, writes
    # reports/analyses/<ts>.md. Pass-1 fires automatically inside
    # `wiki study run` (per-study); Pass-2 runs on its own cadence
    # because it's a different layer of integration. Default OFF
    # until operator flips features.operator_reports.
    "analyst_pass2": ["analyze.py", "--cross-study-only"],
    # Autonomous concept-reconciliation routine (2026-05-22). Double-gated:
    # this legacy piggyback only runs if the operator adds a
    # `piggybacks.concept_reconcile: {enabled: true, ...}` block (default
    # absent → skipped), AND `--apply` is self-gated inside reconcile.py by
    # `features.concept_reconciliation` (off → it falls back to a no-op
    # dry-run). See `.ytstack/backlog/concept-consistency-routine.md`.
    "concept_reconcile": ["reconcile.py", "--apply", "--limit", "{max_per_run}"],
    # Health-trend synthesis (2026-05-23). Deterministic ($0). Double-gated:
    # needs a `piggybacks.health_trends` block (default absent → skipped) AND
    # `features.health_trends` (off → health_trends.py falls back to dry-run).
    "health_trends": ["health_trends.py"],
    # M030 wiki publish — keeps the meinkontext mirror fresh after compile.
    # Double-gated: piggybacks.publish (cadence) AND publish.enabled
    # (--piggyback exits 0 quietly on disabled vaults). Idempotent by
    # content hash — a no-op fire plans zero writes.
    "publish": ["publish/cli.py", "--piggyback"],
}


def build_piggyback_tasks() -> list[dict]:
    """Resolve the enabled piggyback task list from the Collector registry +
    built-in task table, honoring per-task `CONFIG.piggybacks.<name>` gates."""
    tasks: list[dict] = []

    # 1. Registry-discovered Collectors.
    try:
        from collectors import piggyback_collectors  # noqa: WPS433  late import to avoid cycles
    except ImportError:
        def piggyback_collectors():  # type: ignore[misc]
            return []

    for collector in piggyback_collectors():
        name = collector.SPEC.name
        task_cfg = CONFIG.piggybacks.get(name)
        if task_cfg is not None and not task_cfg.enabled:
            continue
        # CONFIG.piggybacks (defaults ⊕ operator overrides) is the cooldown
        # source. The SPEC fallback is defense-in-depth only: every
        # piggyback-default collector has a _default_piggybacks entry with
        # the same cooldown (parity-tested), so task_cfg is never None for
        # a collector shipped with the engine.
        cooldown = task_cfg.cooldown_hours if task_cfg else collector.SPEC.piggyback_cooldown_hours
        cmd = ["collectors/cli.py", name]
        if collector.SPEC.supports_incremental:
            cmd.append("--incremental")
        tasks.append({
            "name": name,
            "cmd": cmd,
            "cooldown_hours": cooldown,
        })

    # 2. Built-in non-Collector tasks.
    for name, cmd_template in _BUILTIN_PIGGYBACK_TASKS.items():
        task_cfg = CONFIG.piggybacks.get(name)
        if task_cfg is None or not task_cfg.enabled:
            continue
        # Avoid double-add if a Collector already claims this name.
        if any(t["name"] == name for t in tasks):
            continue
        cmd = []
        for arg in cmd_template:
            if arg == "{max_per_run}":
                if task_cfg.max_per_run is None:
                    if cmd and cmd[-1] in ("--limit", "-n"):
                        cmd.pop()
                    continue
                cmd.append(str(task_cfg.max_per_run))
            else:
                cmd.append(arg)
        tasks.append({
            "name": name.replace("_", "-"),
            "cmd": cmd,
            "cooldown_hours": task_cfg.cooldown_hours,
        })

    return tasks


def load_piggyback_state() -> dict:
    """Read the persisted `{name: {last_run, status}}` cooldown ledger."""
    import json
    if PIGGYBACK_STATE_FILE.exists():
        try:
            return json.loads(PIGGYBACK_STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def due_tasks(
    *,
    state: dict,
    now: datetime,
    tasks: list[dict],
    after_hour: int,
    ignore_hour_gate: bool,
) -> list[dict]:
    """Pure scheduling decision: which `tasks` should fire right now.

    - Unless `ignore_hour_gate`, returns nothing before `after_hour` (the
      evening-only window the flush path preserves).
    - A task whose `state[name]["last_run"]` is newer than its `cooldown_hours`
      is skipped. A corrupt/absent timestamp fires (never strand a task).
    """
    if not ignore_hour_gate and now.hour < after_hour:
        return []

    due: list[dict] = []
    for task in tasks:
        entry = state.get(task["name"], {})
        last_run = entry.get("last_run")
        if last_run:
            try:
                last_dt = datetime.fromisoformat(last_run)
                elapsed_hours = (now - last_dt).total_seconds() / 3600
                if elapsed_hours < task["cooldown_hours"]:
                    continue
            except (ValueError, TypeError):
                pass  # corrupt timestamp, run anyway
        due.append(task)
    return due


def run_due_piggybacks(
    *,
    ignore_hour_gate: bool = False,
    log: logging.Logger | None = None,
) -> list[str]:
    """Spawn every due piggyback as a detached, wall-clock-capped child.

    `ignore_hour_gate=True` is the compile path (drain whenever the operator
    compiles, cooldown-gated only). `False` is the flush path (evening-only).
    Returns the names spawned. Detached + cooldown-gated, so calling this on
    every compile is safe: a hot loop of compiles can't storm the children.
    """
    log = log or _module_log
    now = datetime.now(ZoneInfo(CONFIG.scheduling.timezone))
    after_hour = CONFIG.scheduling.compile_after_hour

    if not ignore_hour_gate and now.hour < after_hour:
        return []

    state = load_piggyback_state()
    tasks = build_piggyback_tasks()
    pending = due_tasks(
        state=state, now=now, tasks=tasks,
        after_hour=after_hour, ignore_hour_gate=ignore_hour_gate,
    )

    # Wrap each command in piggyback_runner so the child runs under a hard
    # wall-clock cap and its real outcome (ok/failed/timeout) lands in
    # piggyback-state.json. The caller spawns detached and can't wait, so
    # without the runner `status` froze at "spawned" forever and a hung child
    # (e.g. review-wiki on a half-open socket) ran unbounded. See KNOWLEDGE.md.
    from core.piggyback_runner import record_status  # late import — avoid cycles

    runner = SCRIPTS_DIR / "core" / "piggyback_runner.py"
    timeout_s = CONFIG.limits.piggyback_max_runtime_s
    spawned: list[str] = []

    for task in pending:
        name = task["name"]
        script = SCRIPTS_DIR / task["cmd"][0]
        if not script.exists():
            log.warning("Piggyback %s: script not found: %s", name, script)
            continue

        cmd = [sys.executable, str(script)] + task["cmd"][1:]
        wrapped = [sys.executable, str(runner), name, str(timeout_s), "--", *cmd]
        log.info("Piggyback %s: spawning %s (cap %ds)", name, " ".join(task["cmd"]), timeout_s)

        kwargs: dict = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True

        # Record initial state under the SAME lock the runner uses for its
        # running→outcome updates, so neither clobbers the other.
        record_status(name, {"last_run": now.isoformat(timespec="seconds"), "status": "spawned"})

        try:
            subprocess.Popen(
                wrapped,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                **kwargs,
            )
            spawned.append(name)
        except Exception:
            log.exception("Piggyback %s: failed to spawn", name)
            record_status(name, {"status": "error:spawn"})

    return spawned
