"""Context probe for the interactive `wiki` home screen.

Reads vault state cheaply and emits a JSON array of actionable suggestions
to stdout, ranked by priority. The bash entry-point parses the array and
renders it as the "Pending in your vault" section of the home screen.

Design constraints:
    * No LLM, no network, no shell-out.
    * Pure stdlib + the engine's own `core.paths` / `core.config`.
    * Hard 500ms wall-clock cap (SIGALRM); on timeout we emit `[]` so the
      menu falls back to browse-only rendering.
    * Per-probe try/except so a single broken signal never kills the rest.

Output schema (stdout, one line):
    [
      {"key": "1", "count": 3, "label": "3 files in inbox/",
       "cmd": "process-inbox", "priority": 1},
      ...
    ]

Errors and warnings go to stderr. Exit code is always 0 — the bash layer
treats parse failure / empty array as "no suggestions, render browse only".
"""

from __future__ import annotations

import json
import logging
import re
import signal
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.paths import (
    DAILY_DIR,
    INBOX_DIR,
    PEOPLE_DIR,
    PROJECTS_DIR,
    AREAS_DIR,
    RAW_DIR,
    RAW_REQUESTS_DIR,
    RAW_SUGGESTIONS_DIR,
    REPORTS_DIR,
    STATE_FILE,
)

log = logging.getLogger("menu_context")
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

WALL_CLOCK_BUDGET_S = 0.5

# ── Probes ───────────────────────────────────────────────────────────


def probe_inbox() -> int:
    """Count files (any extension) under <vault>/inbox/."""
    if not INBOX_DIR.exists():
        return 0
    return sum(1 for p in INBOX_DIR.iterdir() if p.is_file())


def probe_compile_changed() -> int:
    """Count source files newer than the last `compile` run.

    Uses mtime against `state.json["last_compile"]` rather than re-hashing
    every source — cheap, good-enough for a suggestion (compile itself
    re-hashes for the authoritative diff).
    """
    last_compile_mtime = _last_compile_mtime()
    sources = list(RAW_DIR.rglob("*.md")) + list(DAILY_DIR.rglob("*.md"))
    if last_compile_mtime is None:
        # Never compiled yet — every source is "changed".
        return len(sources)
    return sum(1 for p in sources if p.stat().st_mtime > last_compile_mtime)


def _last_compile_mtime() -> float | None:
    try:
        if not STATE_FILE.exists():
            return None
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        iso = state.get("last_compile")
        if not iso:
            return None
        return datetime.fromisoformat(iso).timestamp()
    except (OSError, ValueError, json.JSONDecodeError) as e:
        log.warning("could not read last_compile from state.json: %s", e)
        return None


def probe_curiosity_pending() -> int:
    """Count `raw/requests/*.json` whose status != 'done'."""
    if not RAW_REQUESTS_DIR.exists():
        return 0
    n = 0
    for p in RAW_REQUESTS_DIR.glob("request-*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if data.get("status") != "done":
                n += 1
        except (OSError, json.JSONDecodeError):
            continue
    return n


def probe_suggestions_approved() -> int:
    """Count actions in `raw/suggestions/*.yaml` with status='approved'."""
    if not RAW_SUGGESTIONS_DIR.exists():
        return 0
    n = 0
    for p in RAW_SUGGESTIONS_DIR.glob("*.yaml"):
        try:
            text = p.read_text(encoding="utf-8")
            # Cheap regex over the file rather than full YAML parse — avoids
            # the yaml import cost on cold start. Format: `status: approved`.
            n += len(re.findall(r"^\s*status:\s*approved\s*$", text, re.MULTILINE))
        except OSError:
            continue
    return n


def probe_dream_overdue() -> int:
    """Count entity pages whose `last_synthesized_at` is past the cooldown.

    Reads `scheduling.dream_cooldown_days` from config (default 7d). Pages
    without `last_synthesized_at:` count as overdue (never synthesized).
    """
    cooldown_days = _read_dream_cooldown_days()
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=cooldown_days)
    n = 0
    for d in (PEOPLE_DIR, PROJECTS_DIR, AREAS_DIR):
        if not d.exists():
            continue
        for p in d.glob("*.md"):
            ts = _read_frontmatter_field(p, "last_synthesized_at")
            if ts is None:
                n += 1
                continue
            try:
                when = datetime.fromisoformat(ts)
                if when.tzinfo is None:
                    when = when.replace(tzinfo=timezone.utc)
                if when < cutoff:
                    n += 1
            except ValueError:
                # Malformed timestamp — count as overdue so the operator notices.
                n += 1
    return n


def _read_dream_cooldown_days() -> int:
    try:
        from core.config import CONFIG  # lazy: heavier import path

        return int(CONFIG.scheduling.dream_cooldown_days)
    except Exception as e:
        log.warning("could not read dream_cooldown_days from CONFIG: %s", e)
        return 7


def _read_frontmatter_field(path: Path, field: str) -> str | None:
    """Cheap frontmatter scan — reads first ~2KB only, no YAML parse."""
    try:
        with path.open("r", encoding="utf-8") as f:
            head = f.read(2048)
    except OSError:
        return None
    if not head.startswith("---"):
        return None
    end = head.find("\n---", 3)
    if end < 0:
        return None
    block = head[3:end]
    m = re.search(rf"^{re.escape(field)}:\s*(.+)$", block, re.MULTILINE)
    if not m:
        return None
    return m.group(1).strip().strip('"').strip("'")


def probe_flush_missing() -> int:
    """1 if today's `daily/sessions/YYYY-MM-DD.md` is missing, else 0."""
    today = datetime.now().strftime("%Y-%m-%d")
    target = DAILY_DIR / "sessions" / f"{today}.md"
    return 0 if target.exists() else 1


def probe_lint_stale() -> int:
    """1 if the newest lint report is older than the newest knowledge/ file.

    A stale lint is a soft signal — knowledge has changed since the last
    structural sweep, worth re-running the cheap structural-only check.
    """
    if not REPORTS_DIR.exists():
        return 1  # never linted
    lints = sorted(REPORTS_DIR.glob("lint-*.md"))
    if not lints:
        return 1
    newest_lint_mtime = max(p.stat().st_mtime for p in lints)
    try:
        from core.paths import KNOWLEDGE_DIR

        newest_knowledge_mtime = max(
            (p.stat().st_mtime for p in KNOWLEDGE_DIR.rglob("*.md")), default=0
        )
    except (OSError, ValueError):
        return 0
    return 1 if newest_knowledge_mtime > newest_lint_mtime else 0


# ── Signal table ─────────────────────────────────────────────────────


def build_suggestions() -> list[dict]:
    """Run all probes, return list of dicts ordered by declared priority.

    Each entry has: key, count, label, cmd, priority. Only entries with
    count > 0 are returned. Keys are auto-numbered "1".."N" after sort.
    """
    raw = [
        ("inbox",       probe_inbox,                1,
         lambda n: f"{n} file{'s' if n != 1 else ''} in inbox/",          "process-inbox"),
        ("compile",     probe_compile_changed,      2,
         lambda n: f"{n} source{'s' if n != 1 else ''} changed since compile", "compile"),
        ("curiosity",   probe_curiosity_pending,    3,
         lambda n: f"{n} curiosity request{'s' if n != 1 else ''} pending",    "curiosity --run-oldest"),
        ("suggestions", probe_suggestions_approved, 4,
         lambda n: f"{n} approved suggestion{'s' if n != 1 else ''} to execute", "suggestions"),
        ("dream",       probe_dream_overdue,        5,
         lambda n: f"{n} entit{'ies' if n != 1 else 'y'} overdue for dream",    "dream --all-entities"),
        ("flush",       probe_flush_missing,        6,
         lambda _: "today's session has not been flushed",                       "flush"),
        ("lint",        probe_lint_stale,           7,
         lambda _: "knowledge edits since last lint sweep",                      "lint --structural-only"),
    ]
    results = []
    for name, probe, priority, label_fn, cmd in raw:
        try:
            n = probe()
        except Exception as e:
            log.warning("probe %s failed: %s", name, e)
            continue
        if n <= 0:
            continue
        results.append({
            "count": n,
            "label": label_fn(n),
            "cmd": cmd,
            "priority": priority,
        })
    results.sort(key=lambda r: r["priority"])
    for i, r in enumerate(results, start=1):
        r["key"] = str(i)
    return results


# ── Entry point ──────────────────────────────────────────────────────


def _timeout_handler(signum, frame):
    raise TimeoutError("menu_context wall-clock budget exhausted")


def main() -> int:
    start = time.monotonic()
    suggestions: list[dict] = []
    # SIGALRM only exists on POSIX; this script doesn't ship to Windows.
    signal.signal(signal.SIGALRM, _timeout_handler)
    signal.setitimer(signal.ITIMER_REAL, WALL_CLOCK_BUDGET_S)
    try:
        suggestions = build_suggestions()
    except TimeoutError:
        log.warning("hit %.0fms cap, returning empty list", WALL_CLOCK_BUDGET_S * 1000)
        suggestions = []
    except Exception as e:
        log.warning("unexpected probe failure: %s", e)
        suggestions = []
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    elapsed_ms = int((time.monotonic() - start) * 1000)
    log.debug("menu_context produced %d suggestions in %dms", len(suggestions), elapsed_ms)
    json.dump(suggestions, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
