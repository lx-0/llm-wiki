"""Flush a Claude Code conversation context into a daily log.

Spawned as a background process by hooks.
Usage: uv run python flush.py <context_file.md> <session_id>
"""

# Must be set BEFORE importing claude_agent_sdk so the SDK knows
# this process was invoked programmatically, not by a human.
import os

os.environ["CLAUDE_INVOKED_BY"] = "memory_flush"

# Strip the DYING parent session's wiring vars (CLAUDE_CODE_SSE_PORT,
# MESSAGING_SOCKET, …) BEFORE the SDK import — hook-spawned flushes inherit
# dead endpoints. Hygiene, NOT the 2026-08 outage cause (that was host-MCP
# schema injection; the run_sdk_query harness isolates it). The harness
# sanitizes again per call; this module-level pass also covers the
# compile.py / piggyback children this process spawns, which inherit its
# env. sdk_helpers is import-light (no SDK pull).
from core.sdk_helpers import sanitize_stale_session_env

sanitize_stale_session_env(os.environ)

import argparse
import asyncio
import contextlib
import logging
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# ── Paths & constants ────────────────────────────────────────────────
SCRIPTS_DIR = Path(__file__).resolve().parent
WIKI_DIR = SCRIPTS_DIR.parent
ROOT_DIR = WIKI_DIR.parent

from core import flush_pipeline
from core.config import CONFIG
from core.console import setup_console_logging
from core.entry import child_env, python_m
from core.piggybacks import run_due_piggybacks
from core.sdk_helpers import FailureClass, SdkCallSpec, is_fatal, run_sdk_query
from core.state_store import StateStore, is_ingested, store_for, try_locked

# The context's turn headings (`hooks/_transcript.py`). A reply that carries them continued
# the session instead of distilling it — 46 such blocks sit in the live daily/ (45 Claude
# Code, 1 Codex; last 2026-09-04), permanent because the context is deleted after a write
# (M034-S06-T07).
_TRANSCRIPT_TURN = re.compile(r"^## (User|Assistant)\s*$", re.MULTILINE)
# A distill is sections under headings (`flush_extract.md`), at the prompt's H2 or at H1. A
# reply with none answered the session's last message instead ("Ehrlich: …", live
# daily/2026-09-05).
_SECTION = re.compile(r"^#{1,6} \S", re.MULTILINE)
# The prompt's one reply for a conversation with nothing worth keeping: the context is
# consumed and no block written. As a failure it would wait in the retry archive for good.
NOTHING_TO_SAVE = "NOTHING_TO_SAVE"

DAILY_DIR = ROOT_DIR / "daily"
STATE_DIR = WIKI_DIR / "state"  # *.json runtime artifacts (hash trackers, cooldowns)
LOGS_DIR = WIKI_DIR / "logs"  # *.log files
STATE_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE = LOGS_DIR / "flush.log"
ERRORS_LOG_FILE = LOGS_DIR / "flush-errors.log"
LAST_FLUSH_FILE = STATE_DIR / "last-flush.json"
# Children are spawned as modules (core.entry) — handler paths relative to scripts/.
COMPILE_HANDLER = "compile.py"
DASHBOARD_STATS_HANDLER = "dashboard/dashboard_stats.py"
DASHBOARD_LINT_HANDLER = "dashboard/dashboard_lint.py"
DASHBOARD_LOCK_FILE = STATE_DIR / "dashboard-refresh.lock"
# 30s was too tight on iCloud-synced vaults under post-compile-hour
# concurrent-flush bursts (incident 2026-05-03: 103 timeout records in
# ~30 seconds). The dashboard scripts themselves take 5-15 s in steady
# state but cross 120 s on a growing vault under iCloud fs-stat variance
# (29 timeouts observed) — now a CONFIG knob (default 300 s). The refresh
# is lock-guarded + best-effort; a timeout just skips it, never blocks flush.
DASHBOARD_REFRESH_TIMEOUT_S = CONFIG.limits.dashboard_refresh_timeout_s
TIMEZONE = CONFIG.scheduling.timezone
COMPILE_AFTER_HOUR = CONFIG.scheduling.compile_after_hour
DEDUP_WINDOW_SECONDS = CONFIG.scheduling.dedup_window_seconds
# PIGGYBACK_STATE_FILE + the task table + spawn logic now live in
# core/piggybacks.py so compile.py can drain due maintenance without importing
# this module (which pulls the Claude SDK + sets CLAUDE_INVOKED_BY at load).

# Re-exports — kept so retry_failed_flushes.py and any other importers
# continue to find the canonical paths/funcs at familiar names.
SESSIONS_DIR = flush_pipeline.SESSIONS_DIR
FAILED_FLUSHES_DIR = flush_pipeline.FAILED_DIR
append_to_daily = flush_pipeline.append_to_daily

log = logging.getLogger("flush")


# ── Dedup helpers ────────────────────────────────────────────────────


def _last_flush_store() -> StateStore:
    """`last-flush.json` (session id → flush stamp, the dedup window) through the seam:
    parallel SessionEnd hooks are the recorded concurrent-writer class, so every write is
    a locked merge into what is on disk at write time. Resolved per call (tests repoint
    the file)."""
    return store_for(LAST_FLUSH_FILE)


def _is_duplicate(session_id: str) -> bool:
    """Return True if this session was flushed within the dedup window."""
    last_ts = _last_flush_store().reload().get(session_id)
    if last_ts is None:
        return False
    return (time.time() - last_ts) < DEDUP_WINDOW_SECONDS


def _record_flush(session_id: str) -> None:
    stamp = time.time()
    cutoff = stamp - 3600  # prune entries older than 1 hour to keep the file small

    def _merge(d: dict) -> None:
        for stale in [k for k, v in d.items() if v <= cutoff]:
            del d[stale]
        d[session_id] = stamp

    _last_flush_store().update(_merge)


# ── Extraction ───────────────────────────────────────────────────────

from core.prompts import render

MAX_RETRIES = CONFIG.limits.flush_max_retries
RETRY_DELAY = CONFIG.limits.flush_retry_delay_seconds


def _misshapen(reply: str) -> FailureClass:
    """Why a reply the call returned is still no distill — a failed attempt, never written."""
    if _TRANSCRIPT_TURN.search(reply):
        return FailureClass(
            "transcript_echo",
            "the reply continued the session's transcript (## User / ## Assistant turns) "
            "instead of distilling it — not written",
        )
    return FailureClass(
        "no_sections",
        "the reply has no section — it answered the conversation instead of distilling "
        "it — not written",
    )


async def extract_from_context(context: str) -> str | None:
    """Use Claude to extract structured knowledge from a conversation context.

    Returns the distill (sections under headings), `NOTHING_TO_SAVE` when the
    conversation holds nothing worth keeping, or ``None`` when every attempt
    failed — an SDK failure or a reply in the wrong shape (`_misshapen`).

    Runs through the one SDK harness (`run_sdk_query`), not a hand-rolled
    `query()` loop. The harness classifies a structured error — a
    ``ResultMessage(is_error=True)`` whose ``result`` text IS the API's
    message — and logs it with its cause. The old loop only saw exceptions:
    from 2026-09-09 to 09-17 every flush (Claude Code and Codex alike) died
    as `cli_crash · exited silently` when the real answer, "Claude Code
    2.1.97 does not support this model; version 2.1.251 or newer is
    required", had been on stdout the whole time. It also guards the
    success path: with SDK 0.2.x a refused call comes back as
    ``subtype="success", is_error=True`` — the old ``subtype == "success"``
    check would have appended the API error text to daily/ as the session
    summary.

    Fatal kinds (auth / model / cli_outdated) stop the retry ladder on the
    first attempt: they fail identically until the operator intervenes, and
    three attempts × 30 s sleeps per session only delayed the archive.
    """
    prompt = render("flush_extract", context=context)

    last_failure = None
    for attempt in range(1, MAX_RETRIES + 1):
        spec = SdkCallSpec(
            label=f"flush_extract attempt {attempt}/{MAX_RETRIES}",
            logger=log,
            system_prompt=render("flush_extract_system"),
            # `tools=()` → `--tools ""` (empty BASE toolset): the agent has NO
            # tools. `allowed_tools=()` is falsy and the SDK transport skips
            # it, leaving the default toolset active — which once turned this
            # summarization call into an agentic Grep/Read loop over the
            # substrate (kind=unknown failures + ~$0.4/call).
            tools=(),
            max_turns=3,
            setting_sources=(),
            input_chars=len(context),
            # Host-MCP isolation (mcp_servers={} + --strict-mcp-config) is the
            # harness default — the 2026-08-14→25 outage root cause (M031-S01).
        )
        outcome = await run_sdk_query(prompt, spec)
        reply = outcome.result_text or ""
        if outcome.ok:
            if reply.strip().strip("`") == NOTHING_TO_SAVE:
                return NOTHING_TO_SAVE
            if _SECTION.search(reply) and not _TRANSCRIPT_TURN.search(reply):
                return reply

        last_failure = outcome.failure or _misshapen(reply)
        if outcome.ok:
            # The harness logged the call a success. The doctor's flush check names the
            # newest failure from this shape — `kind=` after the label, as the harness has it.
            log.warning(
                "%s ✗ reply rejected — kind=%s · %s",
                spec.label,
                last_failure.kind,
                last_failure.detail,
            )
        if is_fatal(last_failure):
            log.error(
                "Claude extraction failed with a fatal kind=%s — not retrying "
                "(fails identically until fixed): %s",
                last_failure.kind,
                last_failure.detail,
            )
            return None
        if attempt < MAX_RETRIES:
            log.warning(
                "Retrying in %ds (last kind=%s)...",
                RETRY_DELAY,
                last_failure.kind,
            )
            await asyncio.sleep(RETRY_DELAY)
        else:
            log.error(
                "Claude extraction failed after %d attempts (last kind=%s)",
                MAX_RETRIES,
                last_failure.kind,
            )
            return None
    return None


# ── Compile trigger ──────────────────────────────────────────────────


def maybe_trigger_compile(daily_file: Path) -> None:
    """Trigger compile.py as a detached background process if it's after COMPILE_AFTER_HOUR
    and the daily log has changed since last compile."""
    now = datetime.now(ZoneInfo(TIMEZONE))
    if now.hour < COMPILE_AFTER_HOUR:
        log.info("Skipping compile — current hour %d < %d", now.hour, COMPILE_AFTER_HOUR)
        return

    # Skip when the file's content is already in the ingested ledger. The
    # ledger schema (ROOT_DIR-relative key → plain content-hash string) lives
    # in core.state_store — the previous hand-rolled reader here keyed by
    # DAILY_DIR-relative path AND expected `{"hash": ...}` dict values
    # (double schema drift vs compile.py's writes), so its skip branch could
    # never fire and every evening flush unconditionally spawned compile.
    try:
        if is_ingested(daily_file):
            log.info("Skipping compile — %s unchanged since last compile", daily_file.name)
            return
    except (OSError, ValueError):
        pass  # unreadable/corrupt state — fail open; compile re-checks the ledger

    log.info("Triggering compile for %s", daily_file.name)
    cmd = python_m(COMPILE_HANDLER, "--file", str(daily_file))

    kwargs: dict = {}
    if sys.platform == "win32":
        # Windows: CREATE_NEW_PROCESS_GROUP to detach
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        # Unix: start_new_session to detach from parent
        kwargs["start_new_session"] = True

    try:
        subprocess.Popen(
            cmd,
            env=child_env(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            **kwargs,
        )
    except Exception:
        log.exception("Failed to spawn compile.py")


# ── Dashboard refresh ───────────────────────────────────────────────


@contextlib.contextmanager
def _dashboard_refresh_lock():
    """Non-blocking lock so concurrent SessionEnd hooks don't all spawn
    their own dashboard refresh (`core.state_store.try_locked` + skip-log).

    Symptom on 2026-05-03: 103 `subprocess.TimeoutExpired` records in
    ~30s, all clustered around the post-compile-hour trigger when
    multiple flush hooks fired in quick succession on an iCloud-synced
    vault. The refresh is idempotent and best-effort, so the cheapest
    fix is to serialize: first flush wins the lock, others skip — the
    next flush picks up the latest state anyway.
    """
    with try_locked(DASHBOARD_LOCK_FILE) as acquired:
        if not acquired:
            log.info(
                "dashboard refresh: another flush holds the lock — skipping (idempotent, next flush will retry)"
            )
        yield acquired


def _run_dashboard_script(handler: str, label: str) -> None:
    """Run one dashboard regen module, logging structured diagnostics on
    failure so the operator can tell timeouts apart from crashes."""
    started = time.time()
    try:
        result = subprocess.run(
            python_m(handler),
            env=child_env(),
            capture_output=True,
            stdin=subprocess.DEVNULL,
            check=False,
            timeout=DASHBOARD_REFRESH_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired as exc:
        elapsed = time.time() - started
        log.error(
            "dashboard %s refresh TIMEOUT after %.1fs (limit=%ds) — %s",
            label,
            elapsed,
            DASHBOARD_REFRESH_TIMEOUT_S,
            handler,
        )
        if exc.stderr:
            log.error("    stderr: %s", exc.stderr.decode("utf-8", errors="replace")[:500])
        return
    except Exception:
        log.exception("dashboard %s refresh: spawn failed", label)
        return
    elapsed = time.time() - started
    if result.returncode != 0:
        log.warning(
            "dashboard %s refresh failed (exit=%d, %.1fs): %s",
            label,
            result.returncode,
            elapsed,
            result.stderr.decode("utf-8", errors="replace")[:500],
        )
    else:
        log.info("dashboard %s refresh ok (%.1fs)", label, elapsed)


def refresh_dashboard_stats() -> None:
    """Regenerate `_dashboard-stats.md` so the vault Dashboard reflects
    the counts after this flush. Best-effort: never blocks the flush."""
    with _dashboard_refresh_lock() as acquired:
        if not acquired:
            return
        _run_dashboard_script(DASHBOARD_STATS_HANDLER, "stats")


def refresh_dashboard_lint() -> None:
    """Regenerate `_dashboard-lint.md` so the vault Dashboard reflects
    the lint queues after this flush. Best-effort."""
    with _dashboard_refresh_lock() as acquired:
        if not acquired:
            return
        _run_dashboard_script(DASHBOARD_LINT_HANDLER, "lint")


# ── Piggyback tasks ─────────────────────────────────────────────────


def maybe_run_piggyback_tasks() -> None:
    """Spawn due piggyback tasks (evening-only, cooldown-gated).

    Thin wrapper over `core.piggybacks.run_due_piggybacks` — the flush path
    keeps the `compile_after_hour` gate. The compile path calls
    `run_due_piggybacks(ignore_hour_gate=True)` directly so daytime compiles
    still drain maintenance. Logic + task table live in core/piggybacks.py.
    """
    run_due_piggybacks(ignore_hour_gate=False, log=log)


# ── Main ─────────────────────────────────────────────────────────────


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="wiki flush",
        description="Extract a daily entry with the Claude Agent SDK (LLM cost applies).",
        epilog=(
            "Use only a disposable UTF-8 Markdown copy of conversation context. "
            "The file is deleted after success, duplicate-skip, empty input or a "
            "conversation with nothing worth keeping; failed extraction moves it to "
            ".wiki/sessions/failed-flushes/. "
            "Evening flushes may also trigger compilation and piggyback tasks."
        ),
    )
    parser.add_argument(
        "context_file",
        type=Path,
        metavar="context_file.md",
        help="disposable conversation context: requests, decisions and outcomes",
    )
    parser.add_argument("session_id", help="capture identity used for deduplication")
    args = sys.argv[1:] if argv is None else argv
    if not args:
        parser.print_help(sys.stderr)
        parser.exit(2)
    return parser.parse_args(args)


async def main() -> None:
    # Shared console setup: TTY-detected colors on stderr, INFO+ archive to
    # LOG_FILE, WARNING+ archive to ERRORS_LOG_FILE. Hook invocations are
    # non-TTY → plain stderr (silently captured by the hook); manual
    # `wiki flush` from a TTY gets the colorized output.
    setup_console_logging("flush", log_file=LOG_FILE, error_file=ERRORS_LOG_FILE)
    args = _parse_args()
    context_file = args.context_file
    session_id = args.session_id

    log.info("flush start — session=%s context=%s", session_id, context_file)

    # Dedup check
    if _is_duplicate(session_id):
        log.info("Skipping duplicate flush for session %s", session_id)
        context_file.unlink(missing_ok=True)
        return

    # Read context
    if not context_file.exists():
        log.error("Context file not found: %s", context_file)
        sys.exit(1)

    context = context_file.read_text(encoding="utf-8")
    if not context.strip():
        log.warning("Empty context file, skipping")
        context_file.unlink(missing_ok=True)
        return

    # Extract
    log.info("Extracting from %d chars of context", len(context))
    extracted = await extract_from_context(context)

    # Recognise the staged file shape so we can route success/failure
    # through the canonical pipeline. A non-matching path (legacy or
    # caller-constructed) is wrapped as a synthetic StagedFlush so the
    # pipeline helpers still work uniformly.
    staged = flush_pipeline.parse_name(context_file) or flush_pipeline.StagedFlush(
        path=context_file,
        session_id=session_id,
        kind="session-end",
        created=int(time.time()),
    )

    if extracted == NOTHING_TO_SAVE:
        log.info("Nothing worth keeping in session %s — no daily block", session_id)
        flush_pipeline.mark_complete(staged)
        _record_flush(session_id)
        return

    if not extracted:
        try:
            archive_path = flush_pipeline.archive_failure(staged)
            log.warning("Extraction failed — archived context to %s for retry", archive_path)
        except OSError:
            log.exception("Failed to archive context file")
        return

    daily_file = flush_pipeline.append_to_daily(extracted, session_id)
    log.info("Appended to %s", daily_file)

    flush_pipeline.mark_complete(staged)
    log.info("Deleted temp file: %s", staged.path)

    # Record flush for dedup
    _record_flush(session_id)

    # Append-only history event for Dashboard P2 charts.
    from core.utils import append_history

    append_history(
        "flush",
        session_id=session_id,
        daily_file=str(daily_file.relative_to(ROOT_DIR)),
    )

    # Maybe trigger compilation
    maybe_trigger_compile(daily_file)

    # Refresh `_dashboard-stats.md` so the vault Dashboard reflects this flush.
    refresh_dashboard_stats()

    # Refresh `_dashboard-lint.md` (lint queues) right after stats.
    refresh_dashboard_lint()

    # Maybe run piggyback tasks (email scan, lint, review)
    maybe_run_piggyback_tasks()

    log.info("flush complete — session=%s", session_id)


if __name__ == "__main__":
    asyncio.run(main())
