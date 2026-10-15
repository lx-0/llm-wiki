"""Vault-health checks of the knowledge pipeline: compile errors and state, the corpus,
the index, session flushes, the piggyback scheduler."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from core.health._base import CheckResult, _humanize_delta, _humanize_mtime, _probe_failed
from core.paths import KNOWLEDGE_DIR, LOGS_DIR, ROOT_DIR, STATE_DIR, STATE_FILE, WIKI_DIR


def check_compile_errors_recent() -> CheckResult:
    """Warning if compile-errors.log has entries from the last 7 days."""
    try:
        err_log = LOGS_DIR / "compile-errors.log"
        if not err_log.exists() or err_log.stat().st_size == 0:
            return CheckResult(
                id="compile-errors-recent",
                category="pipeline",
                severity="ok",
                message="no recent compile errors",
            )
        cutoff = time.time() - 7 * 86400
        if err_log.stat().st_mtime < cutoff:
            return CheckResult(
                id="compile-errors-recent",
                category="pipeline",
                severity="ok",
                message=f"compile-errors.log untouched for >7d (last write {_humanize_mtime(err_log)})",
            )
        # Count error/warning lines since the cutoff. Cheap regex-count.
        recent = 0
        with err_log.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                m = re.match(r"^(\d{4}-\d{2}-\d{2})", line)
                if not m:
                    continue
                try:
                    dt = datetime.fromisoformat(m.group(1) + "T00:00:00")
                except ValueError:
                    continue
                if dt.timestamp() >= cutoff and ("ERROR" in line or "WARNING" in line):
                    recent += 1
        if recent == 0:
            return CheckResult(
                id="compile-errors-recent",
                category="pipeline",
                severity="ok",
                message="no error lines in last 7d",
            )
        return CheckResult(
            id="compile-errors-recent",
            category="pipeline",
            severity="warning",
            message=f"{recent} error line{'s' if recent != 1 else ''} in compile-errors.log (last 7d)",
            fix=f"tail {err_log.relative_to(ROOT_DIR)}",
            details={"count": recent, "path": str(err_log.relative_to(ROOT_DIR))},
        )
    except Exception as exc:
        return _probe_failed("compile-errors-recent", "pipeline", exc)


def check_no_knowledge_articles() -> CheckResult:
    """Info if knowledge/ has no .md files (fresh vault)."""
    try:
        if not KNOWLEDGE_DIR.exists():
            return CheckResult(
                id="no-knowledge-articles",
                category="pipeline",
                severity="info",
                message="knowledge/ directory missing",
            )
        n = sum(1 for p in KNOWLEDGE_DIR.rglob("*.md") if p.name not in ("index.md", "log.md"))
        if n == 0:
            return CheckResult(
                id="no-knowledge-articles",
                category="pipeline",
                severity="info",
                message="0 articles yet (fresh vault — drop a source and run `wiki compile`)",
            )
        return CheckResult(
            id="no-knowledge-articles",
            category="pipeline",
            severity="ok",
            message=f"{n} articles",
            details={"count": n},
        )
    except Exception as exc:
        return _probe_failed("no-knowledge-articles", "pipeline", exc)


def check_compile_state() -> CheckResult:
    """Info if state.json missing last_compile OR last_compile > 30d ago."""
    try:
        if not STATE_FILE.exists():
            return CheckResult(
                id="compile-state",
                category="pipeline",
                severity="info",
                message="no compile state yet (run `wiki compile` after first source)",
            )
        import json

        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        iso = state.get("last_compile")
        if not iso:
            return CheckResult(
                id="compile-state",
                category="pipeline",
                severity="info",
                message="state.json has no last_compile field",
            )
        try:
            ts = datetime.fromisoformat(iso).timestamp()
        except ValueError:
            return CheckResult(
                id="compile-state",
                category="pipeline",
                severity="warning",
                message=f"unparseable last_compile timestamp: {iso!r}",
            )
        delta = time.time() - ts
        if delta > 30 * 86400:
            return CheckResult(
                id="compile-state",
                category="pipeline",
                severity="info",
                message=f"last compile {int(delta / 86400)}d ago (consider `wiki compile`)",
                title=f"Your wiki hasn't been updated in {int(delta / 86400)} days",
                fix="wiki compile",
                dispatch_args=["compile"],
            )
        return CheckResult(
            id="compile-state",
            category="pipeline",
            severity="ok",
            message=f"last compile {_humanize_delta(delta)}",
        )
    except Exception as exc:
        return _probe_failed("compile-state", "pipeline", exc)


# ── Reliability checks (M031-S04) ───────────────────────────────────
# The 2026-08-25 audit found three silent-failure classes doctor never
# surfaced: a piggyback stuck on a failed/timeout outcome, substrates dark
# for weeks (no fire, nothing flagging it), and knowledge/index.md drifting
# from the corpus. Each is a warning here, not critical — the vault still
# functions, but the operator is losing intake/navigation silently.


def _parse_ts(raw: object) -> datetime | None:
    """Local-ISO timestamps from piggyback_runner/flush; naive → local tz."""
    if not isinstance(raw, str) or not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return dt.astimezone() if dt.tzinfo is None else dt


def _piggyback_tasks() -> list[dict]:
    """The scheduler's own task list — `{name, cooldown_hours, cmd}` per task.

    THE source of truth for both the state-file key and the cadence: built-in
    tasks persist under `name.replace('_','-')` (config `review_wiki` → state
    `review-wiki`), and the list already excludes disabled tasks and
    collectors that aren't registered. Iterating CONFIG.piggybacks instead
    reported 12 healthy tasks as "never ran" on the live vault (2026-08-26).
    """
    from core.piggybacks import build_piggyback_tasks

    return build_piggyback_tasks()


@dataclass
class _PiggybackAudit:
    """The accumulators of one pass over the scheduler's tasks."""

    results: list[CheckResult] = field(default_factory=list)
    never_ran: list[str] = field(default_factory=list)
    stale: list[tuple[str, datetime, int]] = field(default_factory=list)
    all_runs: list[datetime] = field(
        default_factory=list
    )  # every task's last_run, for the idle test
    healthy: int = 0


def check_piggyback_health(
    *, state_file: Path | None = None, now: datetime | None = None
) -> list[CheckResult]:
    """Piggyback outcome + substrate-freshness audit over piggyback-state.json.

    Per task the SCHEDULER would fire, first matching condition wins:
      - last completed run failed/timeout/error → warning (with last_error)
      - status running/spawned past the runner's wall-clock cap (+1h slack)
        → warning (orphaned runner — the runner records `timeout` at the cap)
      - last fire older than max(factor × cooldown, stale_min_hours)
        → warning (substrate dark)
    Never-ran tasks aggregate into one info line; all healthy → one ok line.

    The phases: the state file → the scheduler's tasks → `_audit_task` per task →
    `_stale_results` (one idle-pipeline finding, or one per dark task) → the never-ran
    and healthy lines.
    """
    from core.config import CONFIG

    now = now or datetime.now().astimezone()
    sf = state_file or (STATE_DIR / "piggyback-state.json")
    state: dict = {}
    if sf.exists():
        try:
            state = json.loads(sf.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return [
                CheckResult(
                    id="piggyback-health",
                    category="pipeline",
                    severity="warning",
                    message=f"piggyback state unreadable: {sf.name}",
                    fix="inspect the file; the runner rewrites it on the next fire",
                )
            ]

    cap_s = int(getattr(CONFIG.limits, "piggyback_max_runtime_s", 14_400))
    stale_factor = int(getattr(CONFIG.limits, "doctor_piggyback_stale_factor", 4))
    stale_floor_s = int(getattr(CONFIG.limits, "doctor_piggyback_stale_min_hours", 24)) * 3600

    try:
        tasks = _piggyback_tasks()
    except Exception as exc:
        return [_probe_failed("piggyback-health", "pipeline", exc)]

    audit = _PiggybackAudit()
    for task in sorted(tasks, key=lambda t: str(t.get("name", ""))):
        _audit_task(
            task,
            state,
            audit,
            now=now,
            cap_s=cap_s,
            stale_factor=stale_factor,
            stale_floor_s=stale_floor_s,
        )

    if audit.stale:
        audit.results.extend(_stale_results(audit, now=now, stale_floor_s=stale_floor_s))

    if audit.never_ran:
        audit.results.append(
            CheckResult(
                id="piggyback-never-ran",
                category="pipeline",
                severity="info",
                message=f"piggyback(s) never ran yet: {', '.join(audit.never_ran)}",
            )
        )
    if not audit.results or audit.healthy:
        audit.results.append(
            CheckResult(
                id="piggyback-health",
                category="pipeline",
                severity="ok",
                message=f"{audit.healthy} piggyback(s) healthy (last fires within cadence)",
            )
        )
    return audit.results


def _audit_task(
    task: dict,
    state: dict,
    audit: _PiggybackAudit,
    *,
    now: datetime,
    cap_s: int,
    stale_factor: int,
    stale_floor_s: int,
) -> None:
    """One scheduler task, first matching condition wins: a failed / timeout last run,
    a running / spawned status past the runner's cap, a last fire past the stale
    threshold — else healthy. A task without a state entry never ran."""
    name = str(task.get("name", ""))
    cooldown_hours = int(task.get("cooldown_hours") or 0)
    entry = state.get(name)
    if not isinstance(entry, dict):
        audit.never_ran.append(name)
        return
    status = str(entry.get("status") or "")
    last_error = entry.get("last_error")
    started = _parse_ts(entry.get("started"))
    last_run = _parse_ts(entry.get("last_run")) or _parse_ts(entry.get("ended"))
    if last_run is not None:
        audit.all_runs.append(last_run)

    if status == "timeout" or status.startswith(("failed:", "error:")):
        detail = f" — {last_error}" if last_error else ""
        audit.results.append(
            CheckResult(
                id=f"piggyback-{name}",
                category="pipeline",
                severity="warning",
                message=f"piggyback {name}: last run {status}{detail}",
                fix="next compile retries after cooldown; logs in .wiki/logs/",
            )
        )
        return
    if (
        status in ("running", "spawned")
        and started is not None
        and (now - started).total_seconds() > cap_s + 3600
    ):
        audit.results.append(
            CheckResult(
                id=f"piggyback-{name}",
                category="pipeline",
                severity="warning",
                message=(
                    f"piggyback {name}: {status} since {started:%Y-%m-%d %H:%M} "
                    "— past the runner's wall-clock cap (orphaned?)"
                ),
                fix="check the pid in piggyback-state.json; kill leftovers",
            )
        )
        return
    # Piggybacks only fire when the operator compiles/flushes, so a short
    # cadence alone can't define staleness — any normal quiet stretch
    # would flag every 1h task (live false positive: voice at 12h).
    stale_after_s = max(stale_factor * cooldown_hours * 3600, stale_floor_s)
    if last_run is not None and (now - last_run).total_seconds() > stale_after_s:
        audit.stale.append((name, last_run, cooldown_hours))
        return
    audit.healthy += 1


def _stale_results(
    audit: _PiggybackAudit, *, now: datetime, stale_floor_s: int
) -> list[CheckResult]:
    """The stale tasks as findings.

    One idle pipeline is ONE finding. Because every piggyback fires from the
    same trigger, an operator who simply hasn't compiled for two days used to
    get a warning per task — eight of them, all restating one fact, which
    trains the reader to skim the banner (live 2026-08-27). A task that is
    dark while OTHERS fired recently is the opposite: genuinely broken, and
    still reported on its own."""
    results: list[CheckResult] = []
    # "Has the pipeline fired at all lately?" — the newest last_run across
    # EVERY task, stale or not. Not "are some tasks non-stale": a weekly
    # task sits comfortably inside a 28-day threshold without having run,
    # so counting those as evidence of a live pipeline suppressed the
    # collapse entirely on the live vault (2026-08-27).
    newest_fire = max(audit.all_runs, default=None)
    pipeline_idle = newest_fire is not None and (now - newest_fire).total_seconds() > stale_floor_s
    if pipeline_idle and len(audit.stale) >= 3:
        age_days = (now - newest_fire).total_seconds() / 86_400
        results.append(
            CheckResult(
                id="piggyback-pipeline-idle",
                category="pipeline",
                severity="warning",
                message=(
                    f"pipeline idle for {age_days:.1f}d — {len(audit.stale)} piggyback(s) "
                    f"past their cadence ({', '.join(n for n, _, _ in audit.stale[:4])}"
                    f"{'…' if len(audit.stale) > 4 else ''})"
                ),
                fix="run `wiki compile` — piggybacks drain from it (piggybacks_on_compile)",
                details={"stale": [n for n, _, _ in audit.stale]},
            )
        )
    else:
        for name, last_run, cooldown_hours in audit.stale:
            age_days = (now - last_run).total_seconds() / 86_400
            results.append(
                CheckResult(
                    id=f"piggyback-{name}",
                    category="pipeline",
                    severity="warning",
                    message=(
                        f"piggyback {name}: no fire for {age_days:.1f}d "
                        f"(cadence {cooldown_hours}h) — substrate dark"
                    ),
                    fix="run `wiki compile` (piggybacks_on_compile) or check flush.py runs",
                )
            )
    return results


def check_index_drift(
    *, quick: bool = False, knowledge_dir: Path | None = None, vault: Path | None = None
) -> CheckResult:
    """Dry-run `core.index_sync` against the corpus; drift → warn + `wiki reindex`.

    Walks every knowledge/ article (first-paragraph reads), so it is skipped
    in --quick mode.
    """
    if quick:
        return CheckResult(
            id="index-drift",
            category="pipeline",
            severity="info",
            message="index drift check skipped (--quick)",
        )
    knowledge = knowledge_dir or KNOWLEDGE_DIR
    if not knowledge.exists():
        return CheckResult(
            id="index-drift",
            category="pipeline",
            severity="info",
            message="no knowledge/ yet — index drift not applicable",
        )
    try:
        from core.index_sync import sync_index

        stats = sync_index(
            knowledge,
            vault or ROOT_DIR,
            today=datetime.now().astimezone().date().isoformat(),
            apply=False,
        )
    except Exception as exc:
        return _probe_failed("index-drift", "pipeline", exc)
    if stats.get("changed"):
        return CheckResult(
            id="index-drift",
            category="pipeline",
            severity="warning",
            message=(
                f"knowledge/index.md drift: {stats.get('deduped', 0)} duplicate / "
                f"{stats.get('dropped_dangling', 0)} dangling / "
                f"{stats.get('appended', 0)} missing row(s)"
            ),
            title="Your note list is out of date",
            fix="wiki reindex",
            dispatch_args=["reindex"],
        )
    return CheckResult(
        id="index-drift",
        category="pipeline",
        severity="ok",
        message=f"knowledge/index.md in sync ({stats.get('kept', 0)} rows)",
    )


# ── flush pipeline ──────────────────────────────────────────────────
#
# 2026-09-09→17: every session flush (Claude Code AND Codex) died for eight
# days and nothing on the operator's surface said so. The hooks fired,
# flush.log filled with `cli_crash`, 446 contexts piled up in
# failed-flushes/, daily/ simply stopped growing — and the operator found
# out by asking whether Codex was "even hooked up". This check reads the
# TAILS of flush.log + flush-errors.log (they are multi-MB, iCloud-synced;
# never the whole file on the doctor path), counts the archive, and names
# the last classified failure so the remedy is in the message.

_FLUSH_LOG_TAIL_BYTES = 512 * 1024
# Spawns needed after the last success before "stalled" fires — one or two
# unfinished flushes right after a success are just in flight.
_FLUSH_STALL_MIN_SPAWNS = 3
_RE_LOG_LINE_TS = re.compile(r"^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})")
_RE_FLUSH_FAILURE_KIND = re.compile(r"flush_extract.*?kind=([a-z_]+)(?:\s+·\s+(.*))?$")
_FLUSH_FIX_BY_KIND: dict[str, tuple[str, list[str] | None]] = {
    "cli_outdated": (
        "run `wiki update` — the bundled Claude CLI is below the API's version "
        "floor; the engine must ship a newer claude-agent-sdk (see CHANGELOG)",
        ["update"],
    ),
    "auth": ("claude /login (or set ANTHROPIC_API_KEY)", None),
    "model": ("check `models.*` in .wiki/config.yaml against the API's model list", None),
    "rate_limit": ("wait — retries drain via the retry_failed_flushes piggyback", None),
}


def _tail_text(path: Path, max_bytes: int) -> str:
    """Last ``max_bytes`` of a log as text, first partial line dropped."""
    size = path.stat().st_size
    with path.open("rb") as f:
        if size > max_bytes:
            f.seek(size - max_bytes)
        data = f.read()
    text = data.decode("utf-8", errors="replace")
    if size > max_bytes:
        text = text.split("\n", 1)[-1]
    return text


def _log_line_ts(line: str) -> float | None:
    """Naive-local timestamp of a flush.log / flush-errors.log line. Both
    ``2026-09-16 21:02:27,890 [hook] …`` and ``2026-09-16T21:02:28  INFO``
    shapes occur in the same file."""
    m = _RE_LOG_LINE_TS.match(line)
    if not m:
        return None
    try:
        return datetime.fromisoformat(f"{m.group(1)}T{m.group(2)}").timestamp()
    except ValueError:
        return None


def _last_flush_failure(err_log: Path) -> tuple[float | None, str | None, str | None]:
    """(timestamp, kind, detail) of the newest classified flush_extract
    failure line, or (None, None, None)."""
    if not err_log.exists() or err_log.stat().st_size == 0:
        return None, None, None
    for line in reversed(_tail_text(err_log, _FLUSH_LOG_TAIL_BYTES).splitlines()):
        m = _RE_FLUSH_FAILURE_KIND.search(line)
        if not m:
            continue
        ts = _log_line_ts(line)
        if ts is None:
            continue
        return ts, m.group(1), (m.group(2) or "").strip() or None
    return None, None, None


def _newest_sessions_capture_mtime() -> float | None:
    """mtime of the newest ``daily/<date>/sessions.md`` — the artifact a
    landed flush writes (replace-in-place per session). Ground truth for
    "when did a flush last land", independent of how far back the log tail
    reaches: on the lxw vault 512 KB of flush.log covered two days of a
    stall and the last `Appended to` line was eight days back."""
    daily = ROOT_DIR / "daily"
    if not daily.is_dir():
        return None
    newest: float | None = None
    for p in daily.glob("*/sessions.md"):
        try:
            m = p.stat().st_mtime
        except OSError:
            continue
        if newest is None or m > newest:
            newest = m
    return newest


def check_flush_pipeline() -> CheckResult:
    """Critical when flushes keep being spawned but none lands and the
    newest classified failure is younger than the last success; warning
    while an archive of failed contexts is waiting for retry; ok otherwise.

    "Last success" is the newer of the log's last `Appended to` line and the
    newest `daily/*/sessions.md` mtime, so a log tail that no longer reaches
    the last good flush does not read as "never".
    """
    flush_log = LOGS_DIR / "flush.log"
    err_log = LOGS_DIR / "flush-errors.log"
    failed_dir = WIKI_DIR / "sessions" / "failed-flushes"
    archived = sum(1 for p in failed_dir.iterdir() if p.is_file()) if failed_dir.exists() else 0
    if not flush_log.exists() or flush_log.stat().st_size == 0:
        return CheckResult(
            id="flush-pipeline",
            category="pipeline",
            severity="ok",
            message="no session flushed yet (flush.log absent)",
            details={"archived": archived},
        )

    last_ok: float | None = None
    spawns: list[float] = []
    for line in _tail_text(flush_log, _FLUSH_LOG_TAIL_BYTES).splitlines():
        if "Appended to " in line:
            ts = _log_line_ts(line)
            if ts is not None:
                last_ok = ts
        elif "Spawned flush.py" in line:
            ts = _log_line_ts(line)
            if ts is not None:
                spawns.append(ts)
    landed = _newest_sessions_capture_mtime()
    if landed is not None and (last_ok is None or landed > last_ok):
        last_ok = landed
    spawns_since_ok = sum(1 for ts in spawns if ts > (last_ok or 0.0))
    fail_ts, fail_kind, fail_detail = _last_flush_failure(err_log)
    details = {
        "archived": archived,
        "last_success": (
            datetime.fromtimestamp(last_ok).isoformat(timespec="seconds") if last_ok else None
        ),
        "spawns_since_success": spawns_since_ok,
        "last_failure_kind": fail_kind,
    }
    since = _humanize_delta(time.time() - last_ok) if last_ok else "none found"

    stalled = (
        fail_ts is not None
        and fail_ts > (last_ok or 0.0)
        and spawns_since_ok >= _FLUSH_STALL_MIN_SPAWNS
    )
    if stalled:
        cause = f"kind={fail_kind}"
        if fail_detail:
            cause += f" · {fail_detail}"
        fix, dispatch = _FLUSH_FIX_BY_KIND.get(
            fail_kind or "",
            ("tail -50 .wiki/logs/flush-errors.log", None),
        )
        return CheckResult(
            id="flush-pipeline",
            category="pipeline",
            severity="critical",
            message=(
                f"flush pipeline stalled — last successful flush {since}, "
                f"{spawns_since_ok} spawned since, {archived} archived; "
                f"last failure: {cause}"
            ),
            title="Saving your AI chats has stalled",
            fix=fix,
            dispatch_args=dispatch,
            details=details,
        )
    if archived:
        return CheckResult(
            id="flush-pipeline",
            category="pipeline",
            severity="warning",
            message=(
                f"{archived} archived flush context(s) awaiting retry "
                f"(last successful flush {since})"
            ),
            title=f"{archived} AI chat{'s' if archived != 1 else ''} waiting to be saved",
            fix="drains via the retry_failed_flushes piggyback after the next "
            "successful flush or `wiki compile`",
            details=details,
        )
    return CheckResult(
        id="flush-pipeline",
        category="pipeline",
        severity="ok",
        message=f"last flush landed {since}",
        details=details,
    )
