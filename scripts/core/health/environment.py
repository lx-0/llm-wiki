"""Vault-health checks of the operator's environment and integrations: setup, agent
hooks, the `wiki` shortcut, Ollama, Claude auth, per-account OAuth tokens, the voice
transcription toolchain."""

from __future__ import annotations

import os
import re
import socket
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

from core.health._base import CheckResult, _probe_failed
from core.paths import ROOT_DIR, STATE_DIR, STATE_FILE, WIKI_DIR

# Ceiling on the doctor's Ollama TCP probe. The operator's
# `limits.ollama_connect_timeout_s` is sized for real calls (10 s is generous
# on a LAN); the health screen only needs enough headroom to clear jitter, and
# must not stall for ten seconds when the box is genuinely off. Not a config
# knob: it bounds doctor's own latency, not the engine's network behaviour,
# and the operator already controls the value it caps.
_OLLAMA_PROBE_CAP_S = 3.0


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
                title="Finish setting up your wiki",
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
    wiki_hook_re = re.compile(r"\.wiki['\"/ ].*hooks/(session-(start|end)|pre-compact|_transcript)")
    try:
        agent_files = [
            (".claude", "settings.json"),
            (".codex", "hooks.json"),
            (".gemini", "settings.json"),
            (".cursor", "hooks.json"),
        ]
        installed_user: list[str] = []
        installed_project: list[str] = []
        stale_env_agents: list[str] = []
        for agent_dir, filename in agent_files:
            for _scope, root, target in (
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
                    if "UV_PROJECT_ENVIRONMENT=" not in text:
                        stale_env_agents.append(agent_dir.lstrip("."))
        if installed_user or installed_project:
            parts = []
            if installed_user:
                parts.append(f"user: {', '.join(installed_user)}")
            if installed_project:
                parts.append(f"project: {', '.join(installed_project)}")
            # Environment parity: when the engine runs from an out-of-vault
            # environment (UV_PROJECT_ENVIRONMENT, exported by the `wiki`
            # dispatcher for cloud-synced vaults), the installed hook
            # commands must carry it literally — the agent spawns them with
            # ITS env, not ours. Hooks without it run flush/compile from the
            # in-vault environment iCloud keeps evicting (lxw 2026-09-17).
            stale_env = sorted(set(stale_env_agents))
            if os.environ.get("UV_PROJECT_ENVIRONMENT") and stale_env:
                return CheckResult(
                    id="hooks-installed",
                    category="config",
                    severity="warning",
                    message=(
                        f"hooks installed ({'; '.join(parts)}) but "
                        f"{', '.join(stale_env)} still run the engine from the "
                        "in-vault environment (no UV_PROJECT_ENVIRONMENT in the "
                        "hook command)"
                    ),
                    fix="wiki hooks install (rewrites the hook commands with the environment path)",
                    details={
                        "user": installed_user,
                        "project": installed_project,
                        "stale_env": stale_env,
                    },
                )
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
            # "AI assistant chats", never "session capture": the GUI shows this next to the
            # screen/audio capture state, and the two must not read as one thing; "session"
            # alone meant nothing to a first-run reader either (blind panel, 2026-10-15).
            title="AI chats aren't being saved",
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
            float(getattr(getattr(CONFIG, "limits", None), "ollama_connect_timeout_s", 10)),
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
                message=(
                    f"ollama unreachable at {url} "
                    f"(to turn local AI off: `wiki config set models.ollama_url ''`)"
                ),
                # The GUI shows title + fix; the fix is the one plain action, the config
                # alternative stays in the message for the TUI — a shell command in a GUI
                # hint read as "this app will turn into a terminal" (blind panel, 2026-10-15).
                title="The local AI helper (Ollama) isn't reachable",
                fix=f"start Ollama on {host}",
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
            ("gmeet", "gmeet-api", "gmeet-token-", "gmeet-auth"),
        ]
        results: list[CheckResult] = []
        for account_id, account_data in accounts.items():
            if not isinstance(account_data, dict):
                continue
            for block_key, expected_kind, token_prefix, auth_cmd in oauth_integrations:
                block = account_data.get(block_key)
                if not isinstance(block, dict) or block.get("kind") != expected_kind:
                    continue
                results.append(
                    _check_one_token(
                        account_id,
                        block_key,
                        token_prefix,
                        auth_cmd,
                    )
                )
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
                results.append(
                    _check_one_token(
                        account_id,
                        "gmail",
                        "gmail-token-",
                        "gmail-auth",
                    )
                )
            elif filt.get("kind") == "gmail-api":
                # ONLY the write-side filter (suggestions label/move) uses the
                # Gmail API; the reader is IMAP/App-Password, so email READING is
                # unaffected. Report info (not warning) with accurate wording so
                # this stops reading as a broken collector + a wrong re-auth
                # prompt.
                results.append(
                    _check_one_token(
                        account_id,
                        "gmail",
                        "gmail-token-",
                        "gmail-auth",
                        role_desc="email reading via IMAP is unaffected; only the "
                        "suggestions label/move filter is skipped",
                        missing_severity="info",
                    )
                )
        return results
    except Exception as exc:
        return [_probe_failed("account-auths", "connectivity", exc)]


def _check_one_token(
    account_id: str,
    kind_label: str,
    token_prefix: str,
    auth_cmd: str,
    *,
    role_desc: str | None = None,
    missing_severity: str = "warning",
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
            details={"account": account_id, "kind": kind_label, "token_path": str(token_file)},
        )
    role = role_desc or f"the {kind_label} collector will skip it"
    return CheckResult(
        id=check_id,
        category="connectivity",
        severity=missing_severity,
        message=f"{kind_label} OAuth not bootstrapped for account `{account_id}` — {role}",
        title=f"Sign in to {kind_label} ({account_id})",
        fix=f"wiki {auth_cmd} {account_id}",
        dispatch_args=[auth_cmd, account_id],
        details={"account": account_id, "kind": kind_label, "expected_token": str(token_file)},
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
                title="The wiki command isn't on your PATH",
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
            title="The wiki command points at another vault",
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
                id="voice-audio-setup",
                category="config",
                severity="ok",
                message="voice_inbox not configured — audio ingest n/a",
            )
        inbox = Path(inbox_raw).expanduser()
        if not inbox.exists():
            return CheckResult(
                id="voice-audio-setup",
                category="config",
                severity="ok",
                message=f"voice_inbox not found ({inbox}) — audio ingest n/a",
            )
        # Only the audio half — leave dictation-text alone.
        audio_exts = {".m4a", ".mp4", ".mp3", ".wav", ".flac", ".ogg", ".aac"}
        audio_files = [
            p
            for p in inbox.iterdir()
            if p.is_file() and not p.name.startswith(".") and p.suffix.lower() in audio_exts
        ]
        if not audio_files:
            return CheckResult(
                id="voice-audio-setup",
                category="config",
                severity="ok",
                message="no audio files queued in voice_inbox",
            )

        model_raw = (CONFIG.personal.voice_transcribe_model or "").strip()
        if not model_raw:
            return CheckResult(
                id="voice-audio-setup",
                category="config",
                severity="warning",
                message=(
                    f"{len(audio_files)} audio file(s) queued but "
                    f"personal.voice_transcribe_model is empty"
                ),
                fix="set personal.voice_transcribe_model to your ggml model path; see config.example.yaml",
            )
        model_path = Path(model_raw).expanduser()
        if not model_path.is_file():
            return CheckResult(
                id="voice-audio-setup",
                category="config",
                severity="warning",
                message=f"voice_transcribe_model {model_path} does not exist",
                fix="download a ggml model from https://huggingface.co/ggerganov/whisper.cpp/tree/main",
            )

        whisper_cfg = (CONFIG.personal.voice_transcribe_binary or "").strip()
        whisper = whisper_cfg or shutil.which("whisper-cli")
        if not whisper or (whisper_cfg and not Path(whisper_cfg).expanduser().is_file()):
            return CheckResult(
                id="voice-audio-setup",
                category="config",
                severity="warning",
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
                    id="voice-audio-setup",
                    category="config",
                    severity="warning",
                    message="ffmpeg not on $PATH (required for m4a/mp4/aac pre-conversion)",
                    fix="brew install ffmpeg",
                )

        return CheckResult(
            id="voice-audio-setup",
            category="config",
            severity="ok",
            message=f"{len(audio_files)} audio file(s) queued, transcription pipeline ready",
        )
    except Exception as exc:
        return _probe_failed("voice-audio-setup", "config", exc)
