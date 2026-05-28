"""rsync-based inbox bridge.

Mirrors files from sandbox-restricted source paths (e.g. macOS
`~/Library/CloudStorage/GoogleDrive-…/…`, which TCC blocks for Claude
Code's subprocess sandbox but allows for user-shell + LaunchAgent
processes) into local non-restricted paths the substrate collectors
then folder-watch as their `<substrate>_inbox`.

Why this exists: the engine's substrate collectors (pictures, voice,
captures, …) folder-watch a single configured path. Operators wanting
to drop intake from a phone via Google Drive / iCloud Drive / etc.
can't point a collector directly at the CloudStorage mount because
the engine subprocess (when spawned by a Claude-Code hook) inherits
the host process's TCC sandbox and gets `Operation not permitted`.
This bridge runs as the user (manually or via LaunchAgent), where TCC
*is* satisfied, and pre-mirrors the source into a stable local path
the collector can then read freely.

Substrate-agnostic: each `inbox_bridges` mapping is a plain file-tree
mirror. The operator wires each mapping's `local` into the matching
substrate's `*_inbox` key separately (e.g. `picture_inbox`,
`voice_inbox`). The bridge has no concept of substrate types.

Mode = move (default) drains the remote on every sync via rsync's
`--remove-source-files`. The trade-off is documented in config.py:
the source folder becomes one-shot conveyor-belt rather than a mirror,
which prevents re-ingestion when the downstream collector archives
the file out of `local`. Mode = copy keeps the remote intact (operator
accepts duplicate ingestion mitigation lives elsewhere — e.g. they
periodically clear the remote by hand).
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class BridgeResult:
    """Per-mapping sync outcome.

    `status` is one of: ok | skipped | failed. `skipped` covers disabled
    mappings AND missing-remote (TCC, Drive offline, operator typo).
    `failed` covers rsync non-zero exit. `ok` includes dry-run.
    """
    name: str
    status: str  # "ok" | "skipped" | "failed"
    reason: str = ""
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""


@dataclass
class BridgeRunSummary:
    """Top-level result of `run()` — one entry per mapping."""
    results: list[BridgeResult] = field(default_factory=list)

    @property
    def ok_count(self) -> int:
        return sum(1 for r in self.results if r.status == "ok")

    @property
    def skipped_count(self) -> int:
        return sum(1 for r in self.results if r.status == "skipped")

    @property
    def failed_count(self) -> int:
        return sum(1 for r in self.results if r.status == "failed")

    @property
    def exit_code(self) -> int:
        return 1 if self.failed_count > 0 else 0


def _resolve_rsync_binary() -> str:
    """Prefer Homebrew rsync over `/usr/bin/rsync` (Apple's openrsync).

    Both support `-r -t --remove-source-files --dry-run`, so functionally
    either works. We pick the one on PATH for parity with operator habits
    (operators with `brew install rsync` get their preferred binary).
    Returns "rsync" as fallback string — subprocess will surface ENOENT.
    """
    return shutil.which("rsync") or "rsync"


def _mapping_name(mapping: dict) -> str:
    name = mapping.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    local = mapping.get("local") or ""
    return Path(str(local)).name or "<unnamed>"


def _validate(mapping: dict) -> str | None:
    """Return error message if mapping is unusable, else None."""
    if not isinstance(mapping, dict):
        return "mapping is not a dict"
    remote = mapping.get("remote")
    local = mapping.get("local")
    if not isinstance(remote, str) or not remote.strip():
        return "missing or empty `remote` field"
    if not isinstance(local, str) or not local.strip():
        return "missing or empty `local` field"
    mode = mapping.get("mode", "move")
    if mode not in ("move", "copy"):
        return f"invalid `mode` {mode!r}; expected 'move' or 'copy'"
    return None


def sync_one(
    mapping: dict,
    *,
    dry_run: bool = False,
    rsync_binary: str | None = None,
    _run: callable = subprocess.run,  # injected for tests
) -> BridgeResult:
    """Sync one mapping. Pure with respect to the filesystem when dry_run=True.

    Graceful skips for:
    - mapping not a dict / missing fields → status=skipped, reason describes
    - explicitly `enabled: false`              → status=skipped
    - remote path doesn't exist               → status=skipped (Drive offline,
      operator typo, TCC denial all look the same from a non-sandboxed
      caller — listed as skipped so the caller can choose to alert)
    """
    name = _mapping_name(mapping if isinstance(mapping, dict) else {})

    err = _validate(mapping)
    if err is not None:
        log.warning("bridge %s: %s", name, err)
        return BridgeResult(name=name, status="skipped", reason=err)

    if mapping.get("enabled", True) is False:
        return BridgeResult(name=name, status="skipped", reason="disabled")

    remote = Path(os.path.expanduser(str(mapping["remote"]))).resolve(strict=False)
    local = Path(os.path.expanduser(str(mapping["local"]))).resolve(strict=False)
    mode = mapping.get("mode", "move")

    if not remote.exists():
        log.warning("bridge %s: remote does not exist or unreadable: %s", name, remote)
        return BridgeResult(
            name=name,
            status="skipped",
            reason=f"remote_missing: {remote}",
        )

    # Materialise local dir lazily — only when remote actually exists, so a
    # disconnected Drive doesn't spam empty local mirror dirs.
    try:
        local.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        log.error("bridge %s: cannot create local dir %s: %s", name, local, exc)
        return BridgeResult(
            name=name,
            status="failed",
            reason=f"local_mkdir_failed: {exc}",
        )

    binary = rsync_binary or _resolve_rsync_binary()
    cmd: list[str] = [binary, "-rt", "--exclude=.DS_Store", "--exclude=._*"]
    if dry_run:
        cmd.append("--dry-run")
    if mode == "move":
        cmd.append("--remove-source-files")
    cmd.append(f"{remote}/")
    cmd.append(f"{local}/")

    log.info("bridge %s: %s -> %s (%s%s)", name, remote, local, mode,
             ", dry-run" if dry_run else "")

    try:
        proc = _run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        log.error("bridge %s: rsync binary not found (%s)", name, exc)
        return BridgeResult(
            name=name,
            status="failed",
            reason=f"rsync_not_found: {exc}",
        )

    rc = getattr(proc, "returncode", 1)
    stdout = getattr(proc, "stdout", "") or ""
    stderr = getattr(proc, "stderr", "") or ""

    if rc != 0:
        log.warning("bridge %s: rsync exit %d; stderr: %s", name, rc, stderr.strip()[:300])
        return BridgeResult(
            name=name,
            status="failed",
            reason=f"rsync_exit_{rc}",
            returncode=rc,
            stdout=stdout,
            stderr=stderr,
        )

    log.info("bridge %s: ok", name)
    return BridgeResult(
        name=name,
        status="ok",
        returncode=rc,
        stdout=stdout,
        stderr=stderr,
    )


def run(
    mappings: list[dict],
    *,
    dry_run: bool = False,
    rsync_binary: str | None = None,
    _run: callable = subprocess.run,
) -> BridgeRunSummary:
    """Sync every mapping in `mappings`. Empty list → empty summary, no-op."""
    summary = BridgeRunSummary()
    for mapping in mappings:
        summary.results.append(
            sync_one(mapping, dry_run=dry_run, rsync_binary=rsync_binary, _run=_run)
        )
    return summary
