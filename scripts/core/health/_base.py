"""What every vault-health check shares: the result type, the severity order, the
probe-failure funnel and the age humanisers."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

# The package's logger name: the probe-failure funnel logged as `core.health` before the
# checks moved into submodules, and log filters + tests select on it.
log = logging.getLogger("core.health")

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2, "ok": 3}


@dataclass
class CheckResult:
    id: str
    category: str  # "config" / "connectivity" / "pipeline"
    severity: str  # "critical" / "warning" / "info" / "ok"
    message: str
    fix: str | None = None  # human-readable suggestion (shell or prose)
    # When set, the home-screen banner promotes this check into the
    # navigable Actionable list — Enter dispatches `wiki <dispatch_args>`
    # via subprocess. Leave None for checks whose fix is multi-step,
    # shell-only, or external (e.g. "claude /login", "tail …").
    dispatch_args: list[str] | None = None
    details: dict | None = field(default=None)
    # Plain-English phrasing for GUI consumers (desktop app, agents) — set it next to the
    # check that produces operator jargon; `to_json` falls back to `message`. The TUI keeps
    # rendering `message` (DECISIONS 2026-06-24: engine/CLI speak operator, GUI plain).
    title: str | None = None


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
