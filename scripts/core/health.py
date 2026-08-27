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

import json
import logging
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
    STATE_DIR,
    STATE_FILE,
    WIKI_DIR,
)


log = logging.getLogger(__name__)

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2, "ok": 3}

# Ceiling on the doctor's Ollama TCP probe. The operator's
# `limits.ollama_connect_timeout_s` is sized for real calls (10 s is generous
# on a LAN); the health screen only needs enough headroom to clear jitter, and
# must not stall for ten seconds when the box is genuinely off. Not a config
# knob: it bounds doctor's own latency, not the engine's network behaviour,
# and the operator already controls the value it caps.
_OLLAMA_PROBE_CAP_S = 3.0


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

    Skipped in --quick mode — a TCP connect to a dead host costs real
    wall-clock no matter how small the budget.

    The budget derives from `limits.ollama_connect_timeout_s` (capped for the
    health screen, see `_OLLAMA_PROBE_CAP_S`). It used to be a hardcoded
    0.15 s, which is below ordinary LAN jitter: against a healthy host
    answering in 6-41 ms, 2 of 12 connects still exceeded it and were reported
    `unreachable` (measured 2026-08-26). A check that cries wolf on a working
    host is worse than no check — the operator learns to ignore it.
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
        budget = min(
            float(getattr(getattr(CONFIG, "limits", None),
                          "ollama_connect_timeout_s", 10)),
            _OLLAMA_PROBE_CAP_S,
        )
        started = time.monotonic()
        try:
            with socket.create_connection((host, port), timeout=budget):
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


def check_engine_update_available(*, quick: bool = False) -> CheckResult:
    """Warning if local engine HEAD is behind its upstream tracking branch.

    Hits the network (`git fetch`) so skipped under `--quick`. Graceful
    degradation when the engine isn't a git checkout, has no upstream,
    or the fetch fails (offline). When behind, surfaces in the
    home-screen Actionable list with `wiki update` as the dispatch.
    """
    if quick:
        return CheckResult(
            id="engine-update-available",
            category="config",
            severity="info",
            message="(skipped in --quick mode)",
        )
    try:
        if not (WIKI_DIR / ".git").exists():
            return CheckResult(
                id="engine-update-available",
                category="config",
                severity="info",
                message="engine not a git checkout — update via your install method",
            )
        ups = subprocess.run(
            ["git", "-C", str(WIKI_DIR), "rev-parse", "--abbrev-ref", "@{u}"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=2, text=True,
        )
        if ups.returncode != 0:
            return CheckResult(
                id="engine-update-available",
                category="config",
                severity="info",
                message="no upstream tracking branch — skipping update check",
            )
        upstream = ups.stdout.strip()
        fetch = subprocess.run(
            ["git", "-C", str(WIKI_DIR), "fetch", "--quiet", "--no-tags"],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=8, text=True,
        )
        if fetch.returncode != 0:
            return CheckResult(
                id="engine-update-available",
                category="config",
                severity="info",
                message="git fetch failed (offline?) — could not check for updates",
            )
        count = subprocess.run(
            ["git", "-C", str(WIKI_DIR), "rev-list", "--count", f"HEAD..{upstream}"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=2, text=True,
        )
        n = int((count.stdout or "0").strip() or "0")
        if n == 0:
            return CheckResult(
                id="engine-update-available",
                category="config",
                severity="ok",
                message=f"engine up to date with {upstream}",
            )
        latest = subprocess.run(
            ["git", "-C", str(WIKI_DIR), "log", "-1", "--format=%h %s", upstream],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=2, text=True,
        )
        head = (latest.stdout or "").strip()[:80]
        msg = f"{n} engine commit{'s' if n != 1 else ''} behind {upstream}"
        if head:
            msg += f" (latest: {head})"
        return CheckResult(
            id="engine-update-available",
            category="config",
            severity="warning",
            message=msg,
            fix="wiki update",
            dispatch_args=["update"],
            details={"behind": n, "upstream": upstream, "latest": head},
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return _probe_failed("engine-update-available", "config", exc)
    except Exception as exc:
        return _probe_failed("engine-update-available", "config", exc)


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



def check_account_auths(*, quick: bool = False) -> list[CheckResult]:
    """One CheckResult per (account, OAuth-integration) pair declared
    under `personal.accounts.<id>.<block>`.

    Probes for the token cache in `STATE_DIR/<kind>-token-<account-id>.json`.
    Missing token → severity=warning with `dispatch_args=["<kind>-auth",
    "<account-id>"]` so the home-screen banner can run the OAuth bootstrap
    in one keystroke. Token present → severity=ok.

    Three integrations covered today (matches the engine's `<kind>-auth`
    bootstrap commands + `state/<kind>-token-<id>.json` convention):

        block_key       expected `kind`        token prefix       auth cmd
        ──────────      ────────────────────   ───────────────    ───────────────
        calendar        google-calendar        calendar-token-    calendar-auth
        gmeet           gmeet-api              gmeet-token-       gmeet-auth
        reader (sub)    gmail-api              gmail-token-       gmail-auth

    Quick mode is a no-op cost-wise (file-existence probes are sub-ms);
    kept as a kwarg for protocol parity with the other gated checks.

    Returns an empty list when `personal.accounts` is unset / empty —
    multi-tenant story preserved (no account = no auth checks to run).
    """
    try:
        from core.config import CONFIG

        accounts = getattr(CONFIG.personal, "accounts", None) or {}
        # block_key, expected_kind, token_prefix, auth_cmd
        oauth_integrations = [
            ("calendar", "google-calendar", "calendar-token-", "calendar-auth"),
            ("gmeet",    "gmeet-api",       "gmeet-token-",    "gmeet-auth"),
        ]
        results: list[CheckResult] = []
        for account_id, account_data in accounts.items():
            if not isinstance(account_data, dict):
                continue
            for block_key, expected_kind, token_prefix, auth_cmd in oauth_integrations:
                block = account_data.get(block_key)
                if not isinstance(block, dict) or block.get("kind") != expected_kind:
                    continue
                results.append(_check_one_token(
                    account_id, block_key, token_prefix, auth_cmd,
                ))
            # gmail is special: the `gmail-token-<id>.json` cache is
            # consumed by EITHER the reader (mailbox adapter; reads
            # messages via Gmail REST API) OR the filter (suggestions
            # backend; pushes label/move actions via Gmail REST API).
            # An account that declares `kind: gmail-api` on either
            # sub-block needs the OAuth token bootstrapped once.
            reader = account_data.get("reader") or {}
            filt = account_data.get("filter") or {}
            if reader.get("kind") == "gmail-api":
                # reader pulls messages via the Gmail REST API → the token is
                # load-bearing; without it the collector genuinely skips.
                results.append(_check_one_token(
                    account_id, "gmail", "gmail-token-", "gmail-auth",
                ))
            elif filt.get("kind") == "gmail-api":
                # ONLY the write-side filter (suggestions label/move) uses the
                # Gmail API; the reader is IMAP/App-Password, so email READING is
                # unaffected. Report info (not warning) with accurate wording so
                # this stops reading as a broken collector + a wrong re-auth
                # prompt.
                results.append(_check_one_token(
                    account_id, "gmail", "gmail-token-", "gmail-auth",
                    role_desc="email reading via IMAP is unaffected; only the "
                              "suggestions label/move filter is skipped",
                    missing_severity="info",
                ))
        return results
    except Exception as exc:
        return [_probe_failed("account-auths", "connectivity", exc)]


def _check_one_token(
    account_id: str, kind_label: str, token_prefix: str, auth_cmd: str,
    *, role_desc: str | None = None, missing_severity: str = "warning",
) -> CheckResult:
    """Per-account-integration token-presence probe. Caller is the
    iterator in `check_account_auths`; not registered as a standalone
    check (would require knowing which accounts exist at registration time).

    `role_desc` overrides the "what breaks without the token" clause (e.g. for
    gmail, where a missing token skips only the write-side filter while an IMAP
    reader keeps working); `missing_severity` lets such degraded-but-not-broken
    cases report `info` instead of `warning`."""
    token_file = STATE_DIR / f"{token_prefix}{account_id}.json"
    check_id = f"account-auth-{account_id}-{kind_label}"
    if token_file.exists():
        return CheckResult(
            id=check_id,
            category="connectivity",
            severity="ok",
            message=f"{kind_label} OAuth ready for account `{account_id}`",
            details={"account": account_id, "kind": kind_label,
                     "token_path": str(token_file)},
        )
    role = role_desc or f"the {kind_label} collector will skip it"
    return CheckResult(
        id=check_id,
        category="connectivity",
        severity=missing_severity,
        message=f"{kind_label} OAuth not bootstrapped for account "
                f"`{account_id}` — {role}",
        fix=f"wiki {auth_cmd} {account_id}",
        dispatch_args=[auth_cmd, account_id],
        details={"account": account_id, "kind": kind_label,
                 "expected_token": str(token_file)},
    )



def check_wiki_on_path() -> CheckResult:
    """Warning when `wiki` isn't on the operator's $PATH, or when it is
    on PATH but resolves to a DIFFERENT vault's wiki binary than the
    one we're currently running in.

    Without the shortcut, every invocation needs `./.wiki/wiki` or the
    full vault path (especially painful with iCloud-Mobile-Documents
    paths). `wiki install-shortcut` creates `~/.local/bin/wiki` → this
    vault's wiki. The health-check is the discoverability layer for
    operators who never realized the shortcut command exists.
    """
    try:
        import shutil

        own_wiki = WIKI_DIR / "wiki"
        resolved = shutil.which("wiki")
        if resolved is None:
            return CheckResult(
                id="wiki-on-path",
                category="config",
                severity="warning",
                message="`wiki` not on $PATH — every call needs ./.wiki/wiki or full path",
                fix="wiki install-shortcut",
                dispatch_args=["install-shortcut"],
            )
        # `wiki` IS on PATH — but does it point at THIS vault?
        try:
            resolved_target = Path(resolved).resolve()
        except OSError:
            resolved_target = Path(resolved)
        try:
            own_target = own_wiki.resolve()
        except OSError:
            own_target = own_wiki
        if resolved_target == own_target:
            return CheckResult(
                id="wiki-on-path",
                category="config",
                severity="ok",
                message=f"`wiki` on PATH → this vault ({resolved})",
                details={"resolved": resolved, "target": str(own_target)},
            )
        return CheckResult(
            id="wiki-on-path",
            category="config",
            severity="warning",
            message=f"`wiki` on PATH points at a different vault ({resolved_target})",
            fix="wiki install-shortcut",
            dispatch_args=["install-shortcut"],
            details={"resolved": resolved, "this_vault": str(own_target)},
        )
    except Exception as exc:
        return _probe_failed("wiki-on-path", "config", exc)


def check_voice_audio_setup() -> CheckResult:
    """Warning when audio files are queued in voice_inbox but the
    transcription pipeline isn't reachable.

    Three failure shapes the operator cares about:
      1. audio files present + voice_transcribe_model empty → operator
         hasn't enabled audio ingest yet.
      2. audio files present + model configured but path missing →
         setup half-done, file points at a non-existent .bin.
      3. audio files present + model OK but whisper-cli not on PATH →
         brew install whisper-cpp wasn't run.

    Returns `ok` when audio ingest isn't relevant (no audio files
    queued, or no voice_inbox configured at all) — silent on the
    happy-path-without-audio.
    """
    try:
        import shutil

        from core.config import CONFIG

        inbox_raw = (CONFIG.personal.voice_inbox or "").strip()
        if not inbox_raw:
            return CheckResult(
                id="voice-audio-setup", category="config", severity="ok",
                message="voice_inbox not configured — audio ingest n/a",
            )
        inbox = Path(inbox_raw).expanduser()
        if not inbox.exists():
            return CheckResult(
                id="voice-audio-setup", category="config", severity="ok",
                message=f"voice_inbox not found ({inbox}) — audio ingest n/a",
            )
        # Only the audio half — leave dictation-text alone.
        audio_exts = {".m4a", ".mp4", ".mp3", ".wav", ".flac", ".ogg", ".aac"}
        audio_files = [
            p for p in inbox.iterdir()
            if p.is_file() and not p.name.startswith(".") and p.suffix.lower() in audio_exts
        ]
        if not audio_files:
            return CheckResult(
                id="voice-audio-setup", category="config", severity="ok",
                message="no audio files queued in voice_inbox",
            )

        model_raw = (CONFIG.personal.voice_transcribe_model or "").strip()
        if not model_raw:
            return CheckResult(
                id="voice-audio-setup", category="config", severity="warning",
                message=(
                    f"{len(audio_files)} audio file(s) queued but "
                    f"personal.voice_transcribe_model is empty"
                ),
                fix="set personal.voice_transcribe_model to your ggml model path; see config.example.yaml",
            )
        model_path = Path(model_raw).expanduser()
        if not model_path.is_file():
            return CheckResult(
                id="voice-audio-setup", category="config", severity="warning",
                message=f"voice_transcribe_model {model_path} does not exist",
                fix="download a ggml model from https://huggingface.co/ggerganov/whisper.cpp/tree/main",
            )

        whisper_cfg = (CONFIG.personal.voice_transcribe_binary or "").strip()
        whisper = whisper_cfg or shutil.which("whisper-cli")
        if not whisper or (whisper_cfg and not Path(whisper_cfg).expanduser().is_file()):
            return CheckResult(
                id="voice-audio-setup", category="config", severity="warning",
                message="whisper-cli not on $PATH",
                fix="brew install whisper-cpp",
            )

        # ffmpeg only required for non-native formats (m4a/mp4/aac).
        needs_ffmpeg = any(p.suffix.lower() in {".m4a", ".mp4", ".aac"} for p in audio_files)
        if needs_ffmpeg:
            ffmpeg_cfg = (CONFIG.personal.voice_transcribe_ffmpeg or "").strip()
            ffmpeg = ffmpeg_cfg or shutil.which("ffmpeg")
            if not ffmpeg or (ffmpeg_cfg and not Path(ffmpeg_cfg).expanduser().is_file()):
                return CheckResult(
                    id="voice-audio-setup", category="config", severity="warning",
                    message="ffmpeg not on $PATH (required for m4a/mp4/aac pre-conversion)",
                    fix="brew install ffmpeg",
                )

        return CheckResult(
            id="voice-audio-setup", category="config", severity="ok",
            message=f"{len(audio_files)} audio file(s) queued, transcription pipeline ready",
        )
    except Exception as exc:
        return _probe_failed("voice-audio-setup", "config", exc)


# ── Dependency integrity ────────────────────────────────────────────
# A venv can rot into a state that looks installed and isn't: correct
# `.dist-info`, correct version, most modules present — and one subpackage
# missing, so the top-level import raises. Live 2026-08-26 on the operator's
# vault: `httpx` without `_transports/`, `claude_agent_sdk` without
# `mcp.client`, `prompt_toolkit` without a submodule. That is every HTTP
# surface plus compile / flush / dream / publish down at once, and the only
# symptom was a piggyback exiting non-zero with no stderr.
#
# Suspected cause: the vault lives under `~/Library/Mobile Documents/`, so
# iCloud can evict `.venv` file contents. Unproven, and it does not matter
# here — the check is about noticing, not about the cause.

# Distributions whose import name differs from their package name. Only the
# EXCEPTIONS are data; the list itself is derived from pyproject.toml so it
# can never drift from what is actually declared.
_IMPORT_NAME_OVERRIDES: dict[str, str] = {
    "pyyaml": "yaml",
    "python-dotenv": "dotenv",
    "pillow": "PIL",
    "claude-agent-sdk": "claude_agent_sdk",
    "youtube-transcript-api": "youtube_transcript_api",
    "yt-dlp": "yt_dlp",
    "google-auth": "google.auth",
    "google-auth-oauthlib": "google_auth_oauthlib",
    "html2text": "html2text",
    "imapclient": "imapclient",
}


def _declared_import_names() -> list[str]:
    """Import names for every distribution in `pyproject.toml`'s
    `[project].dependencies`, in declaration order."""
    import tomllib

    data = tomllib.loads((WIKI_DIR / "pyproject.toml").read_text(encoding="utf-8"))
    out: list[str] = []
    for spec in data.get("project", {}).get("dependencies", []):
        # "package>=1.2" / "package[extra]==1" → "package"
        dist = re.split(r"[<>=!~\[; ]", str(spec).strip(), maxsplit=1)[0].strip().lower()
        if dist:
            out.append(_IMPORT_NAME_OVERRIDES.get(dist, dist.replace("-", "_")))
    return out


def _failed_imports(names: list[str]) -> list[tuple[str, str]]:
    """Import each name in a SUBPROCESS, return [(name, error)] for failures.

    Out-of-process because a half-installed C extension can abort the
    interpreter — taking doctor down with it — and because importing the
    engine's heavy deps into the doctor process would slow every run.
    """
    if not names:
        return []
    probe = (
        "import importlib, json, sys\n"
        "out = []\n"
        "for n in sys.argv[1:]:\n"
        "    try:\n"
        "        importlib.import_module(n)\n"
        "    except BaseException as exc:\n"
        "        out.append([n, f'{type(exc).__name__}: {exc}'])\n"
        "print(json.dumps(out))\n"
    )
    try:
        proc = subprocess.run(  # noqa: S603 — argv is engine-derived
            [sys.executable, "-c", probe, *names],
            capture_output=True, text=True, timeout=120,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return [("(probe)", f"{type(exc).__name__}: {exc}")]
    try:
        return [(n, e) for n, e in json.loads(proc.stdout or "[]")]
    except (json.JSONDecodeError, TypeError, ValueError):
        # The probe itself died — that IS a broken environment.
        detail = (proc.stderr or "no output").strip().splitlines()[-1:]
        return [("(probe)", detail[0] if detail else "probe produced no output")]


def check_dependencies_importable(*, quick: bool = False) -> CheckResult:
    """Critical if any declared dependency fails to import."""
    if quick:
        return CheckResult(
            id="dependencies-importable", category="config", severity="info",
            message="dependency import check skipped (--quick)",
        )
    try:
        names = _declared_import_names()
    except Exception as exc:  # noqa: BLE001
        return _probe_failed("dependencies-importable", "config", exc)

    failures = _failed_imports(names)
    if not failures:
        return CheckResult(
            id="dependencies-importable", category="config", severity="ok",
            message=f"all {len(names)} declared dependencies import cleanly",
        )
    shown = ", ".join(n for n, _ in failures[:3])
    more = f" (+{len(failures) - 3} more)" if len(failures) > 3 else ""
    return CheckResult(
        id="dependencies-importable", category="config", severity="critical",
        message=f"{len(failures)} declared dependenc(ies) fail to import: {shown}{more}",
        fix=f"cd '{WIKI_DIR}' && uv sync --reinstall",
        details={"failed": [{"module": n, "error": e} for n, e in failures]},
    )


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
    """
    from core.config import CONFIG

    now = now or datetime.now().astimezone()
    sf = state_file or (STATE_DIR / "piggyback-state.json")
    state: dict = {}
    if sf.exists():
        try:
            state = json.loads(sf.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return [CheckResult(
                id="piggyback-health", category="pipeline", severity="warning",
                message=f"piggyback state unreadable: {sf.name}",
                fix="inspect the file; the runner rewrites it on the next fire",
            )]

    cap_s = int(getattr(CONFIG.limits, "piggyback_max_runtime_s", 14_400))
    stale_factor = int(getattr(CONFIG.limits, "doctor_piggyback_stale_factor", 4))
    stale_floor_s = int(getattr(CONFIG.limits, "doctor_piggyback_stale_min_hours", 24)) * 3600

    try:
        tasks = _piggyback_tasks()
    except Exception as exc:
        return [_probe_failed("piggyback-health", "pipeline", exc)]

    results: list[CheckResult] = []
    never_ran: list[str] = []
    healthy = 0
    for task in sorted(tasks, key=lambda t: str(t.get("name", ""))):
        name = str(task.get("name", ""))
        cooldown_hours = int(task.get("cooldown_hours") or 0)
        entry = state.get(name)
        if not isinstance(entry, dict):
            never_ran.append(name)
            continue
        status = str(entry.get("status") or "")
        last_error = entry.get("last_error")
        started = _parse_ts(entry.get("started"))
        last_run = _parse_ts(entry.get("last_run")) or _parse_ts(entry.get("ended"))

        if status == "timeout" or status.startswith(("failed:", "error:")):
            detail = f" — {last_error}" if last_error else ""
            results.append(CheckResult(
                id=f"piggyback-{name}", category="pipeline", severity="warning",
                message=f"piggyback {name}: last run {status}{detail}",
                fix="next compile retries after cooldown; logs in .wiki/logs/",
            ))
            continue
        if status in ("running", "spawned") and started is not None \
                and (now - started).total_seconds() > cap_s + 3600:
            results.append(CheckResult(
                id=f"piggyback-{name}", category="pipeline", severity="warning",
                message=(f"piggyback {name}: {status} since {started:%Y-%m-%d %H:%M} "
                         "— past the runner's wall-clock cap (orphaned?)"),
                fix="check the pid in piggyback-state.json; kill leftovers",
            ))
            continue
        # Piggybacks only fire when the operator compiles/flushes, so a short
        # cadence alone can't define staleness — any normal quiet stretch
        # would flag every 1h task (live false positive: voice at 12h).
        stale_after_s = max(stale_factor * cooldown_hours * 3600, stale_floor_s)
        if last_run is not None and (now - last_run).total_seconds() > stale_after_s:
            age_days = (now - last_run).total_seconds() / 86_400
            results.append(CheckResult(
                id=f"piggyback-{name}", category="pipeline", severity="warning",
                message=(f"piggyback {name}: no fire for {age_days:.1f}d "
                         f"(cadence {cooldown_hours}h) — substrate dark"),
                fix="run `wiki compile` (piggybacks_on_compile) or check flush.py runs",
            ))
            continue
        healthy += 1

    if never_ran:
        results.append(CheckResult(
            id="piggyback-never-ran", category="pipeline", severity="info",
            message=f"piggyback(s) never ran yet: {', '.join(never_ran)}",
        ))
    if not results or healthy:
        results.append(CheckResult(
            id="piggyback-health", category="pipeline", severity="ok",
            message=f"{healthy} piggyback(s) healthy (last fires within cadence)",
        ))
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
            id="index-drift", category="pipeline", severity="info",
            message="index drift check skipped (--quick)",
        )
    knowledge = knowledge_dir or KNOWLEDGE_DIR
    if not knowledge.exists():
        return CheckResult(
            id="index-drift", category="pipeline", severity="info",
            message="no knowledge/ yet — index drift not applicable",
        )
    try:
        from core.index_sync import sync_index

        stats = sync_index(
            knowledge, vault or ROOT_DIR,
            today=datetime.now().astimezone().date().isoformat(),
            apply=False,
        )
    except Exception as exc:
        return _probe_failed("index-drift", "pipeline", exc)
    if stats.get("changed"):
        return CheckResult(
            id="index-drift", category="pipeline", severity="warning",
            message=(f"knowledge/index.md drift: {stats.get('deduped', 0)} duplicate / "
                     f"{stats.get('dropped_dangling', 0)} dangling / "
                     f"{stats.get('appended', 0)} missing row(s)"),
            fix="wiki reindex",
            dispatch_args=["reindex"],
        )
    return CheckResult(
        id="index-drift", category="pipeline", severity="ok",
        message=f"knowledge/index.md in sync ({stats.get('kept', 0)} rows)",
    )


# ── Orchestration ───────────────────────────────────────────────────


# Checks return either a single CheckResult or a list[CheckResult]
# (for multi-result probes like per-account auth — one CheckResult per
# account-integration pair, count knowable only at probe time).
# `build_health` flattens both cases into a single list.
_ALL_CHECKS: list[Callable[..., CheckResult | list[CheckResult]]] = [
    check_setup_run,
    check_hooks_installed,
    check_wiki_on_path,
    check_ollama_reachable,
    check_claude_authed,
    check_account_auths,
    check_compile_errors_recent,
    check_template_drift,
    check_engine_update_available,
    check_no_knowledge_articles,
    check_compile_state,
    check_voice_audio_setup,
    check_piggyback_health,
    check_index_drift,
    check_dependencies_importable,
]


def build_health(*, quick: bool = False) -> list[CheckResult]:
    """Run every check, return results sorted by severity (criticals first).

    Per-check return type is `CheckResult | list[CheckResult]`. Single
    results are appended; lists are extended. Multi-result probes
    (e.g. per-account auth: N accounts × M integrations) handle their
    own iteration internally.
    """
    results: list[CheckResult] = []
    for fn in _ALL_CHECKS:
        try:
            # Pass quick=True only to checks that accept it (introspect signature).
            from inspect import signature

            if "quick" in signature(fn).parameters:
                produced = fn(quick=quick)
            else:
                produced = fn()
            if isinstance(produced, list):
                results.extend(produced)
            else:
                results.append(produced)
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
    # Single funnel for every check's except-clause — the probe failure
    # surfaces in the banner AND leaves a log line (silent-swallow seam).
    log.warning("health probe failed [%s]: %s: %s", id_, type(exc).__name__, exc)
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
