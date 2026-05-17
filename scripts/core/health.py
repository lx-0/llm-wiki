"""Vault-health checks for the home-screen banner + `wiki doctor` surface.

Each check is a pure function returning a `CheckResult`. `build_health()`
runs them all and returns the list, ordered by severity (critical first).
Per-check try/except so a single broken probe never kills the rest;
falls back to a `severity="warning"` result describing the probe failure.

Severities (ordered):
    critical    — wiki is broken / unusable in this state
    warning     — wiki works but a capability is degraded
    info        — informational; often expected (e.g. fresh vault)
    ok          — check passed

`--quick` mode skips network probes + subprocess calls (TCP connect,
`claude --version`, `wiki seed --check`), trading completeness for
sub-50ms latency. Used by hooks where 250ms is too slow.
"""

from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.paths import (
    KNOWLEDGE_DIR,
    LOGS_DIR,
    ROOT_DIR,
    STATE_FILE,
    WIKI_DIR,
)


SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2, "ok": 3}


@dataclass
class CheckResult:
    id: str
    category: str           # "config" / "connectivity" / "pipeline"
    severity: str           # "critical" / "warning" / "info" / "ok"
    message: str
    fix: str | None = None  # human-readable suggestion (shell or prose)
    # When set, the home-screen banner promotes this check into the
    # navigable Actionable list — Enter dispatches `wiki <dispatch_args>`
    # via subprocess. Leave None for checks whose fix is multi-step,
    # shell-only, or external (e.g. "claude /login", "tail …").
    dispatch_args: list[str] | None = None
    details: dict | None = field(default=None)


# ── Individual checks ───────────────────────────────────────────────


def check_setup_run() -> CheckResult:
    """Critical if the operator never ran `wiki setup`.

    Heuristic: `state.json` doesn't exist AND ollama_url is empty AND
    config.yaml hasn't been edited since install (compile_after_hour
    still at the dataclass default 18). False positives possible on
    intentional minimal vaults; tolerable because the fix is a no-op
    when not needed (`wiki setup` is idempotent).
    """
    try:
        from core.config import CONFIG

        state_missing = not STATE_FILE.exists()
        ollama_blank = not (CONFIG.models.ollama_url or "").strip()
        if state_missing and ollama_blank:
            return CheckResult(
                id="setup-not-run",
                category="config",
                severity="critical",
                message="config has default values and no compile state — setup not run",
                fix="wiki setup",
                dispatch_args=["setup"],
            )
        return CheckResult(
            id="setup-not-run",
            category="config",
            severity="ok",
            message="setup wizard completed",
        )
    except Exception as exc:
        return _probe_failed("setup-not-run", "config", exc)


def check_hooks_installed() -> CheckResult:
    """Warning if no wiki-managed hook installs in EITHER scope.

    Both scopes are valid for vault-session capture:
      - USER scope (`~/.<agent>/{settings,hooks}.json`) — fires for
        every agent session machine-wide. Cheapest install, covers
        cwd inside the vault as a side-effect.
      - PROJECT scope (`<vault>/.<agent>/{settings,hooks}.json`) —
        fires only when the agent runs from the vault root. Needed
        when the operator runs the same agent in other projects and
        doesn't want hooks firing there.

    Either is sufficient. Warning fires only when NEITHER scope has
    any wiki-managed entry. Reads each candidate file directly and
    looks for `.wiki/hooks/` in the command text.
    """
    # Match both wiki-hook command styles (parity with lib/agents.sh
    # `hooks_installed`): the current `--project .wiki python
    # .wiki/hooks/session-start.py` form AND the cd-anchored
    # `cd '<abs>/.wiki' && uv run python hooks/session-start.py` form
    # used by earlier engine versions + user-scope installs.
    wiki_hook_re = re.compile(
        r"\.wiki['\"/ ].*hooks/(session-(start|end)|pre-compact|_transcript)"
    )
    try:
        agent_files = [
            (".claude", "settings.json"),
            (".codex", "hooks.json"),
            (".gemini", "settings.json"),
            (".cursor", "hooks.json"),
        ]
        installed_user: list[str] = []
        installed_project: list[str] = []
        for agent_dir, filename in agent_files:
            for scope, root, target in (
                ("user", Path.home(), installed_user),
                ("project", ROOT_DIR, installed_project),
            ):
                path = root / agent_dir / filename
                if not path.exists():
                    continue
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                if wiki_hook_re.search(text):
                    target.append(agent_dir.lstrip("."))
        if installed_user or installed_project:
            parts = []
            if installed_user:
                parts.append(f"user: {', '.join(installed_user)}")
            if installed_project:
                parts.append(f"project: {', '.join(installed_project)}")
            return CheckResult(
                id="hooks-installed",
                category="config",
                severity="ok",
                message=f"hooks installed ({'; '.join(parts)})",
                details={"user": installed_user, "project": installed_project},
            )
        return CheckResult(
            id="hooks-installed",
            category="config",
            severity="warning",
            message="no wiki hooks installed in user or project scope — session capture won't fire",
            fix="wiki hooks install",
            dispatch_args=["hooks", "install"],
        )
    except Exception as exc:
        return _probe_failed("hooks-installed", "config", exc)


def check_ollama_reachable(*, quick: bool = False) -> CheckResult:
    """Warning if `models.ollama_url` is set but the host isn't reachable.

    Skipped in --quick mode (TCP connect with 150ms timeout still costs
    real wall-clock for an unreachable host).
    """
    if quick:
        return CheckResult(
            id="ollama-reachable",
            category="connectivity",
            severity="info",
            message="(skipped in --quick mode)",
        )
    try:
        from core.config import CONFIG

        url = (CONFIG.models.ollama_url or "").strip()
        if not url:
            return CheckResult(
                id="ollama-reachable",
                category="connectivity",
                severity="info",
                message="ollama URL not configured (local LLM features disabled)",
            )
        parsed = urlparse(url)
        host = parsed.hostname or "localhost"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        started = time.monotonic()
        try:
            with socket.create_connection((host, port), timeout=0.15):
                ms = int((time.monotonic() - started) * 1000)
            return CheckResult(
                id="ollama-reachable",
                category="connectivity",
                severity="ok",
                message=f"ollama reachable ({url}, ~{ms}ms)",
                details={"url": url, "latency_ms": ms},
            )
        except (OSError, ValueError):
            return CheckResult(
                id="ollama-reachable",
                category="connectivity",
                severity="warning",
                message=f"ollama unreachable at {url}",
                fix=f"check Ollama is running; or `wiki config set models.ollama_url ''` to disable",
                details={"url": url},
            )
    except Exception as exc:
        return _probe_failed("ollama-reachable", "connectivity", exc)


def check_claude_authed(*, quick: bool = False) -> CheckResult:
    """Warning if there's no plausible Claude auth path.

    Three valid auth paths the engine supports:
      1. `ANTHROPIC_API_KEY` env (direct API)
      2. `~/.claude/.credentials.json` (Claude Code subscription, dot prefix)
      3. Claude Code CLI on PATH (subscription tokens live in macOS Keychain,
         not in a file — `claude --version` is the cheapest liveness test)

    Quick mode skips the `claude --version` subprocess + uses (1) and (2)
    only.
    """
    try:
        env_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if env_key:
            return CheckResult(
                id="claude-authed",
                category="connectivity",
                severity="ok",
                message="ANTHROPIC_API_KEY present in env",
            )
        creds_file = Path.home() / ".claude" / ".credentials.json"
        if creds_file.exists():
            return CheckResult(
                id="claude-authed",
                category="connectivity",
                severity="ok",
                message=f"Claude Code subscription credentials at {creds_file}",
            )
        if quick:
            return CheckResult(
                id="claude-authed",
                category="connectivity",
                severity="warning",
                message="no ANTHROPIC_API_KEY env and no ~/.claude/.credentials.json (CLI not probed in --quick)",
                fix="claude /login or set ANTHROPIC_API_KEY",
            )
        # The CLI being installed AND responsive is a plausible-auth signal
        # for subscription users — tokens live in macOS Keychain, not in a
        # file we can stat. False positive: CLI installed but logged out;
        # `claude --version` still succeeds. Acceptable trade for not
        # spuriously warning every subscription user.
        try:
            subprocess.run(
                ["claude", "--version"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2,
                check=True,
            )
            return CheckResult(
                id="claude-authed",
                category="connectivity",
                severity="ok",
                message="claude CLI on PATH (subscription tokens via OAuth/Keychain assumed)",
            )
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return CheckResult(
                id="claude-authed",
                category="connectivity",
                severity="warning",
                message="claude CLI not found and no API credentials",
                fix="install Claude Code CLI or set ANTHROPIC_API_KEY",
            )
    except Exception as exc:
        return _probe_failed("claude-authed", "connectivity", exc)


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


def check_template_drift(*, quick: bool = False) -> CheckResult:
    """Info if `wiki seed --check` reports drift. Subprocess-based;
    skipped in quick mode."""
    if quick:
        return CheckResult(
            id="template-drift",
            category="config",
            severity="info",
            message="(skipped in --quick mode)",
        )
    try:
        wiki_bin = WIKI_DIR / "wiki"
        if not wiki_bin.exists():
            return CheckResult(
                id="template-drift",
                category="config",
                severity="info",
                message="wiki binary not found — skipping drift check",
            )
        result = subprocess.run(
            [str(wiki_bin), "seed", "--check"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=5,
            text=True,
        )
        drifted = [
            line.split(maxsplit=1)[1].split(" ", 1)[0]
            for line in result.stdout.splitlines()
            if line.lstrip().startswith("drifted ")
        ]
        if not drifted:
            return CheckResult(
                id="template-drift",
                category="config",
                severity="ok",
                message="no template drift",
            )
        return CheckResult(
            id="template-drift",
            category="config",
            severity="info",
            message=f"{len(drifted)} template{'s' if len(drifted) != 1 else ''} drifted from engine (likely operator customization)",
            fix="wiki seed --check for details; `wiki seed --force` to overwrite",
            details={"files": drifted},
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return _probe_failed("template-drift", "config", exc)
    except Exception as exc:
        return _probe_failed("template-drift", "config", exc)


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
        n = sum(
            1
            for p in KNOWLEDGE_DIR.rglob("*.md")
            if p.name not in ("index.md", "log.md")
        )
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


# ── Orchestration ───────────────────────────────────────────────────


_ALL_CHECKS: list[Callable[..., CheckResult]] = [
    check_setup_run,
    check_hooks_installed,
    check_ollama_reachable,
    check_claude_authed,
    check_compile_errors_recent,
    check_template_drift,
    check_no_knowledge_articles,
    check_compile_state,
]


def build_health(*, quick: bool = False) -> list[CheckResult]:
    """Run every check, return results sorted by severity (criticals first)."""
    results: list[CheckResult] = []
    for fn in _ALL_CHECKS:
        try:
            # Pass quick=True only to checks that accept it (introspect signature).
            from inspect import signature

            if "quick" in signature(fn).parameters:
                results.append(fn(quick=quick))
            else:
                results.append(fn())
        except Exception as exc:
            results.append(_probe_failed(fn.__name__, "unknown", exc))
    results.sort(key=lambda r: (SEVERITY_ORDER.get(r.severity, 99), r.id))
    return results


def health_summary(results: list[CheckResult]) -> dict[str, int]:
    """Reduce a check list to severity counts for the banner / JSON payload."""
    out = {"critical": 0, "warning": 0, "info": 0, "ok": 0}
    for r in results:
        out[r.severity] = out.get(r.severity, 0) + 1
    return out


def to_json(results: list[CheckResult]) -> list[dict]:
    """Serialize to plain-dict form for JSON output."""
    return [asdict(r) for r in results]


# ── Internal helpers ────────────────────────────────────────────────


def _probe_failed(id_: str, category: str, exc: Exception) -> CheckResult:
    return CheckResult(
        id=id_,
        category=category,
        severity="warning",
        message=f"probe failed: {exc}",
    )


def _humanize_delta(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s ago"
    if seconds < 3600:
        return f"{int(seconds / 60)}m ago"
    if seconds < 86400:
        return f"{int(seconds / 3600)}h ago"
    return f"{int(seconds / 86400)}d ago"


def _humanize_mtime(p: Path) -> str:
    return _humanize_delta(time.time() - p.stat().st_mtime)
