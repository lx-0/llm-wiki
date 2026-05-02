"""Flush a Claude Code conversation context into a daily log.

Spawned as a background process by hooks.
Usage: uv run python flush.py <context_file.md> <session_id>
"""

# Must be set BEFORE importing claude_agent_sdk so the SDK knows
# this process was invoked programmatically, not by a human.
import os

os.environ["CLAUDE_INVOKED_BY"] = "memory_flush"

import asyncio
import json
import logging
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

# ── Paths & constants ────────────────────────────────────────────────
SCRIPTS_DIR = Path(__file__).resolve().parent
WIKI_DIR = SCRIPTS_DIR.parent
ROOT_DIR = WIKI_DIR.parent
sys.path.insert(0, str(SCRIPTS_DIR))
from wiki_config import CONFIG  # noqa: E402

import flush_pipeline  # noqa: E402

DAILY_DIR = ROOT_DIR / "daily"
STATE_DIR = WIKI_DIR / "state"     # *.json runtime artifacts (hash trackers, cooldowns)
LOGS_DIR = WIKI_DIR / "logs"       # *.log files
STATE_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE = LOGS_DIR / "flush.log"
LAST_FLUSH_FILE = STATE_DIR / "last-flush.json"
COMPILE_SCRIPT = SCRIPTS_DIR / "compile.py"
TIMEZONE = CONFIG.scheduling.timezone
COMPILE_AFTER_HOUR = CONFIG.scheduling.compile_after_hour
DEDUP_WINDOW_SECONDS = CONFIG.scheduling.dedup_window_seconds
PIGGYBACK_STATE_FILE = STATE_DIR / "piggyback-state.json"

# Re-exports — kept so retry-failed-flushes.py and any other importers
# continue to find the canonical paths/funcs at familiar names.
SESSIONS_DIR = flush_pipeline.SESSIONS_DIR
FAILED_FLUSHES_DIR = flush_pipeline.FAILED_DIR
append_to_daily = flush_pipeline.append_to_daily

# Piggyback tasks — spawned after compile_after_hour if cooldown elapsed and
# the task is enabled in wiki/config.yaml. Two sources of truth, merged at
# build time:
#
# 1. Registry-discovered Collectors with `SPEC.piggyback_default=True` —
#    spawned as `cli_collect.py <name>` (the canonical CLI for collectors).
# 2. Legacy commands not yet ported to the Collector pattern — listed
#    explicitly below until they get migrated (M003 candidate).
#
# Cooldown + enabled flag come from CONFIG.piggybacks.<name> for both.

_LEGACY_PIGGYBACK_COMMANDS: dict[str, list[str]] = {
    "lint_structural": ["lint.py", "--structural-only"],
    "review_wiki": ["review-wiki.py"],
    "optimize_claude_md": ["optimize-claude-md.py"],
    "scan_screenshots": ["scan-screenshots.py", "--all", "--limit", "{max_per_run}"],
    "sync_memories": ["sync-memories.py"],
    "retry_failed_flushes": ["retry-failed-flushes.py", "--limit", "{max_per_run}"],
}


def _build_piggyback_tasks() -> list[dict]:
    tasks: list[dict] = []

    # 1. Registry-discovered Collectors.
    try:
        from collectors import piggyback_collectors  # noqa: WPS433  late import to avoid cycles
    except ImportError:
        piggyback_collectors = lambda: []  # type: ignore[assignment]

    for collector in piggyback_collectors():
        name = collector.SPEC.name
        task_cfg = CONFIG.piggybacks.get(name)
        if task_cfg is not None and not task_cfg.enabled:
            continue
        cooldown = task_cfg.cooldown_hours if task_cfg else collector.SPEC.piggyback_cooldown_hours
        cmd = ["cli_collect.py", name]
        if collector.SPEC.supports_incremental:
            cmd.append("--incremental")
        tasks.append({
            "name": name,
            "cmd": cmd,
            "cooldown_hours": cooldown,
        })

    # 2. Legacy commands not yet on the Registry.
    for name, cmd_template in _LEGACY_PIGGYBACK_COMMANDS.items():
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


PIGGYBACK_TASKS = _build_piggyback_tasks()

# ── Logging ──────────────────────────────────────────────────────────
logging.basicConfig(
    filename=str(LOG_FILE),
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("flush")


# ── Dedup helpers ────────────────────────────────────────────────────

def _load_last_flush() -> dict:
    if LAST_FLUSH_FILE.exists():
        try:
            return json.loads(LAST_FLUSH_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_last_flush(data: dict) -> None:
    LAST_FLUSH_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _is_duplicate(session_id: str) -> bool:
    """Return True if this session was flushed within the dedup window."""
    data = _load_last_flush()
    last_ts = data.get(session_id)
    if last_ts is None:
        return False
    return (time.time() - last_ts) < DEDUP_WINDOW_SECONDS


def _record_flush(session_id: str) -> None:
    data = _load_last_flush()
    data[session_id] = time.time()
    # Prune entries older than 1 hour to keep the file small
    cutoff = time.time() - 3600
    data = {k: v for k, v in data.items() if v > cutoff}
    _save_last_flush(data)


# ── Extraction ───────────────────────────────────────────────────────

from prompts import render  # noqa: E402

MAX_RETRIES = CONFIG.limits.flush_max_retries
RETRY_DELAY = CONFIG.limits.flush_retry_delay_seconds


def _stderr_logger(line: str) -> None:
    """Forward CLI stderr lines into our flush.log so failures aren't opaque."""
    log.warning("CLI stderr: %s", line.rstrip())


async def extract_from_context(context: str) -> str | None:
    """Use Claude to extract structured knowledge from a conversation context."""
    prompt = render("flush_extract", context=context)

    for attempt in range(1, MAX_RETRIES + 1):
        result_parts: list[str] = []
        try:
            async for message in query(
                prompt=prompt,
                options=ClaudeAgentOptions(
                    system_prompt=render("flush_extract_system"),
                    allowed_tools=[],
                    max_turns=3,
                    setting_sources=[],
                    stderr=_stderr_logger,
                ),
            ):
                if isinstance(message, ResultMessage):
                    if message.subtype == "success" and message.result:
                        result_parts.append(message.result)
            return "\n".join(result_parts) if result_parts else None
        except Exception:
            if attempt < MAX_RETRIES:
                log.warning(
                    "Claude extraction failed (attempt %d/%d), retrying in %ds...",
                    attempt, MAX_RETRIES, RETRY_DELAY,
                )
                await asyncio.sleep(RETRY_DELAY)
            else:
                log.exception("Claude extraction failed after %d attempts", MAX_RETRIES)
                return None


# ── Compile trigger ──────────────────────────────────────────────────

def maybe_trigger_compile(daily_file: Path) -> None:
    """Trigger compile.py as a detached background process if it's after COMPILE_AFTER_HOUR
    and the daily log has changed since last compile."""
    import hashlib

    now = datetime.now(ZoneInfo(TIMEZONE))
    if now.hour < COMPILE_AFTER_HOUR:
        log.info(
            "Skipping compile — current hour %d < %d", now.hour, COMPILE_AFTER_HOUR
        )
        return

    # Check if daily log has changed since last compile
    state_file = STATE_DIR / "state.json"
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
            ingested = state.get("ingested", {})
            rel = daily_file.name
            if rel in ingested:
                current_hash = hashlib.sha256(daily_file.read_bytes()).hexdigest()[:16]
                if ingested[rel].get("hash") == current_hash:
                    log.info("Skipping compile — %s unchanged since last compile", rel)
                    return
        except (json.JSONDecodeError, OSError):
            pass

    log.info("Triggering compile for %s", daily_file.name)
    cmd = [sys.executable, str(COMPILE_SCRIPT), "--file", str(daily_file)]

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
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            **kwargs,
        )
    except Exception:
        log.exception("Failed to spawn compile.py")


# ── Piggyback tasks ─────────────────────────────────────────────────

def _load_piggyback_state() -> dict:
    if PIGGYBACK_STATE_FILE.exists():
        try:
            return json.loads(PIGGYBACK_STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_piggyback_state(state: dict) -> None:
    PIGGYBACK_STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def maybe_run_piggyback_tasks() -> None:
    """Spawn piggyback tasks if it's after COMPILE_AFTER_HOUR and cooldown has elapsed."""
    now = datetime.now(ZoneInfo(TIMEZONE))
    if now.hour < COMPILE_AFTER_HOUR:
        return

    state = _load_piggyback_state()

    for task in PIGGYBACK_TASKS:
        name = task["name"]
        cooldown_hours = task["cooldown_hours"]

        # Check cooldown
        entry = state.get(name, {})
        last_run = entry.get("last_run")
        if last_run:
            try:
                last_dt = datetime.fromisoformat(last_run)
                elapsed_hours = (now - last_dt).total_seconds() / 3600
                if elapsed_hours < cooldown_hours:
                    log.info(
                        "Piggyback %s: cooldown (%.1fh / %dh), skipping",
                        name, elapsed_hours, cooldown_hours,
                    )
                    continue
            except (ValueError, TypeError):
                pass  # corrupt timestamp, run anyway

        # Build command
        script = SCRIPTS_DIR / task["cmd"][0]
        if not script.exists():
            log.warning("Piggyback %s: script not found: %s", name, script)
            continue

        cmd = [sys.executable, str(script)] + task["cmd"][1:]
        log.info("Piggyback %s: spawning %s", name, " ".join(task["cmd"]))

        kwargs: dict = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True

        try:
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                **kwargs,
            )
            state[name] = {
                "last_run": now.isoformat(timespec="seconds"),
                "status": "spawned",
            }
        except Exception:
            log.exception("Piggyback %s: failed to spawn", name)
            state[name] = {
                "last_run": now.isoformat(timespec="seconds"),
                "status": "error",
            }

    _save_piggyback_state(state)


# ── Main ─────────────────────────────────────────────────────────────

async def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: uv run python flush.py <context_file.md> <session_id>")
        sys.exit(1)

    context_file = Path(sys.argv[1])
    session_id = sys.argv[2]

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
        path=context_file, session_id=session_id, kind="session-end", created=int(time.time()),
    )

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

    # Maybe trigger compilation
    maybe_trigger_compile(daily_file)

    # Maybe run piggyback tasks (email scan, lint, review)
    maybe_run_piggyback_tasks()

    log.info("flush complete — session=%s", session_id)


if __name__ == "__main__":
    asyncio.run(main())
