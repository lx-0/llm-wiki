"""Vault-health checks of the engine checkout itself: template drift, upstream updates,
dependency integrity, engine files in a cloud-synced path."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from core.health._base import CheckResult, _probe_failed
from core.paths import WIKI_DIR


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
            check=False,
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
            capture_output=True,
            timeout=2,
            text=True,
            check=False,
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
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=8,
            text=True,
            check=False,
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
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=2,
            text=True,
            check=False,
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
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=2,
            text=True,
            check=False,
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
            title=f"Engine update available ({n} commit{'s' if n != 1 else ''} behind)",
            fix="wiki update",
            dispatch_args=["update"],
            details={"behind": n, "upstream": upstream, "latest": head},
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return _probe_failed("engine-update-available", "config", exc)
    except Exception as exc:
        return _probe_failed("engine-update-available", "config", exc)


# ── Dependency integrity ────────────────────────────────────────────
# A venv can rot into a state that looks installed and isn't: correct
# `.dist-info`, correct version, most modules present — and one subpackage
# missing, so the top-level import raises. Live 2026-08-26 on the operator's
# vault: `httpx` without `_transports/`, `claude_agent_sdk` without
# `mcp.client`, `prompt_toolkit` without a submodule. That is every HTTP
# surface plus compile / flush / dream / publish down at once, and the only
# symptom was a piggyback exiting non-zero with no stderr.
#
# Cause, proven 2026-09-17: the vault lives under `~/Library/Mobile
# Documents/`, `.wiki/.venv` had drifted from a symlink into a real directory
# inside it, and iCloud evicts file contents there — 2 024 dataless engine
# files at the time, the 200 MB bundled Claude CLI among them. Three crash
# reports the same night: `CODESIGNING · Taskgated Invalid Signature`, i.e.
# the kernel SIGKILLed the CLI when pages of the mapped binary no longer
# matched its signature mid-materialisation. `check_engine_cloud_eviction`
# below reports that state; this check stays about noticing the import rot.

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
        proc = subprocess.run(
            [sys.executable, "-c", probe, *names],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
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
            id="dependencies-importable",
            category="config",
            severity="info",
            message="dependency import check skipped (--quick)",
        )
    try:
        names = _declared_import_names()
    except Exception as exc:
        return _probe_failed("dependencies-importable", "config", exc)

    failures = _failed_imports(names)
    if not failures:
        return CheckResult(
            id="dependencies-importable",
            category="config",
            severity="ok",
            message=f"all {len(names)} declared dependencies import cleanly",
        )
    shown = ", ".join(n for n, _ in failures[:3])
    more = f" (+{len(failures) - 3} more)" if len(failures) > 3 else ""
    return CheckResult(
        id="dependencies-importable",
        category="config",
        severity="critical",
        message=f"{len(failures)} declared dependenc(ies) fail to import: {shown}{more}",
        fix=f"cd '{WIKI_DIR}' && uv sync --reinstall",
        details={"failed": [{"module": n, "error": e} for n, e in failures]},
    )


# ── engine files in a cloud-synced path ─────────────────────────────
#
# The vault may live in iCloud Drive (lxw does); the ENGINE must not run
# from evicted files. Two failure shapes, both seen live 2026-09-17:
#   1. `.wiki/.venv` resolving inside the cloud path → the bundled Claude
#      CLI (200 MB) gets evicted/re-materialised while mapped and the kernel
#      SIGKILLs it (`Taskgated Invalid Signature`); the SDK reports
#      `exit code: -9` and the engine logs kind=cli_killed.
#   2. dataless (evicted) scripts/prompts/templates → every import and
#      render blocks on a download; `claude_agent_sdk` took six minutes to
#      import, `wiki doctor` four.
# The layout that avoids both: venv at ~/.venvs/<name>, addressed
# explicitly. The 2026-08-26 symlink form did not survive on lxw: iCloud's
# reconciliation kept the directory the cloud state already had under
# `.venv` (re-materialised, old content) and shelved the symlink as
# `.venv 2`, its conflict-copy name — nobody touched it by hand. A symlink
# inside an iCloud folder is a layout the sync engine can veto
# (KNOWLEDGE 2026-09-17).

_CLOUD_PATH_MARKERS = ("/Library/Mobile Documents/", "/Library/CloudStorage/")
# BSD `SF_DATALESS` (0x40000000): file contents are not on disk (evicted by a
# cloud provider). `stat.SF_DATALESS` only exists from Python 3.13.
_SF_DATALESS = 0x40000000
# Engine directories that are read on every run and must be resident.
_EVICTION_SCAN_DIRS = ("scripts", "prompts", "templates", "hooks", "lib")


def _is_dataless(st: os.stat_result) -> bool:
    return bool(getattr(st, "st_flags", 0) & _SF_DATALESS)


def _in_cloud_path(p: Path) -> bool:
    s = str(p)
    return any(marker in s for marker in _CLOUD_PATH_MARKERS)


def _count_dataless(root: Path) -> tuple[int, int]:
    """(dataless files, files scanned) under ``root`` — stat only, never a
    read, so the scan itself materialises nothing."""
    dataless = scanned = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ("__pycache__", ".git")]
        for name in filenames:
            try:
                st = os.stat(os.path.join(dirpath, name))
            except OSError:
                continue
            scanned += 1
            if _is_dataless(st):
                dataless += 1
    return dataless, scanned


def _effective_env_dir() -> Path:
    """The environment THIS interpreter runs from — `sys.prefix` is the
    ground truth, whatever the dispatcher, a hook or a manual `uv run`
    resolved. Not `.wiki/.venv`: with UV_PROJECT_ENVIRONMENT set that path
    is at best a stale leftover."""
    try:
        return Path(sys.prefix).resolve()
    except OSError:
        return Path(sys.prefix)


def check_engine_cloud_eviction() -> CheckResult:
    """Critical when the engine runs from an environment inside a
    cloud-synced path; warning when a stale in-vault environment is still
    lying in such a path or engine source files are currently evicted;
    ok otherwise.
    """
    venv_real = _effective_env_dir()
    details: dict = {
        "venv": str(venv_real),
        "venv_in_cloud": _in_cloud_path(venv_real),
        "stale_in_vault_venv": None,
        "dataless": 0,
        "scanned": 0,
    }
    # A real .wiki/.venv that is NOT the running environment: dead weight
    # the sync engine keeps hauling (400 MB on lxw) and a trap for any
    # manual `uv run --project .wiki` without the environment variable.
    in_vault = WIKI_DIR / ".venv"
    stale_in_vault: Path | None = None
    if in_vault.exists() and not in_vault.is_symlink():
        try:
            same = in_vault.resolve() == venv_real
        except OSError:
            same = False
        if not same and _in_cloud_path(in_vault):
            stale_in_vault = in_vault
            details["stale_in_vault_venv"] = str(in_vault)

    dataless = scanned = 0
    for sub in _EVICTION_SCAN_DIRS:
        d = WIKI_DIR / sub
        if d.is_dir():
            n, s = _count_dataless(d)
            dataless += n
            scanned += s
    details["dataless"] = dataless
    details["scanned"] = scanned

    if details["venv_in_cloud"]:
        return CheckResult(
            id="engine-cloud-eviction",
            category="config",
            severity="critical",
            message=(
                f"engine runs from an environment inside a cloud-synced path "
                f"({venv_real}) — evictions SIGKILL the bundled Claude CLI mid-run "
                "(Code Signature Invalid) and stall imports for minutes"
                + (f"; {dataless} engine file(s) evicted right now" if dataless else "")
            ),
            title="The engine runs from cloud-synced storage",
            fix=(
                "run `wiki update` (engine ≥0.5.4 builds the environment at "
                "~/.venvs/<vault>-wiki for cloud-synced vaults), then `wiki hooks install` "
                "so the agent hooks use it too; always start the engine via `wiki …`, "
                "never a bare `uv run --project .wiki`"
            ),
            dispatch_args=["update"],
            details=details,
        )
    if stale_in_vault is not None:
        return CheckResult(
            id="engine-cloud-eviction",
            category="config",
            severity="warning",
            message=(
                f"stale in-vault environment at {stale_in_vault} is no longer used "
                f"(engine runs from {venv_real}) but the sync engine keeps hauling it"
                + (f"; {dataless} engine file(s) evicted right now" if dataless else "")
            ),
            title="A stale engine environment sits inside the vault",
            fix=f"rm -rf '{stale_in_vault}'",
            details=details,
        )
    if dataless:
        return CheckResult(
            id="engine-cloud-eviction",
            category="config",
            severity="warning",
            message=(
                f"{dataless} of {scanned} engine file(s) are evicted from local "
                "storage — imports and prompt renders block on cloud downloads"
            ),
            title="Engine files are evicted from local storage",
            fix=f"brctl download '{WIKI_DIR}' (or open the folder in Finder to re-download)",
            details=details,
        )
    return CheckResult(
        id="engine-cloud-eviction",
        category="config",
        severity="ok",
        message=f"engine environment outside cloud-synced storage ({venv_real})",
        details=details,
    )
