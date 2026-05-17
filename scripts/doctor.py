"""`wiki doctor` — full vault-health audit.

Default output: pretty human-readable report, grouped by category.
With `--json`: machine-readable for agents (use-llm-wiki skill).
With `--quick`: skips network + subprocess checks for sub-50ms latency.

Usage:
    wiki doctor                  full pretty report
    wiki doctor --json           machine-readable (for agents)
    wiki doctor --quick          skip TCP + subprocess probes
    wiki doctor --quick --json   both

Exit code:
    0 — no critical issues
    1 — at least one critical issue
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.health import (
    CheckResult,
    build_health,
    health_summary,
    to_json,
)
from core.paths import ROOT_DIR, WIKI_DIR


# ── ANSI ────────────────────────────────────────────────────────────


_TTY = sys.stdout.isatty()
_RESET = "\033[0m" if _TTY else ""
_DIM = "\033[2m" if _TTY else ""
_BOLD = "\033[1m" if _TTY else ""
_GREEN = "\033[32m" if _TTY else ""
_YELLOW = "\033[33m" if _TTY else ""
_RED = "\033[31m" if _TTY else ""
_CYAN = "\033[36m" if _TTY else ""

_SEVERITY_STYLE = {
    "critical": (f"{_RED}✗{_RESET}", _RED),
    "warning":  (f"{_YELLOW}⚠{_RESET}", _YELLOW),
    "info":     (f"{_DIM}ℹ{_RESET}",    _DIM),
    "ok":       (f"{_GREEN}✓{_RESET}",  ""),
}


# ── Pretty renderer ─────────────────────────────────────────────────


def render_pretty(results: list[CheckResult], summary: dict) -> str:
    vault = ROOT_DIR.name
    revision = _git_revision()
    lines: list[str] = [
        "",
        f"  {_BOLD}Vault health{_RESET} — {vault} vault (commit {revision})",
        "",
    ]

    # Group by category in stable order, but keep severity ordering within each.
    categories: list[tuple[str, list[CheckResult]]] = []
    seen: dict[str, list[CheckResult]] = {}
    for r in results:
        seen.setdefault(r.category, []).append(r)
    for cat in ("config", "connectivity", "pipeline", "unknown"):
        if cat in seen:
            categories.append((cat, seen[cat]))
    # Any unexpected categories last.
    for cat, items in seen.items():
        if cat not in {"config", "connectivity", "pipeline", "unknown"}:
            categories.append((cat, items))

    for cat, items in categories:
        title = {"config": "Config + setup", "connectivity": "Connectivity",
                 "pipeline": "Pipeline", "unknown": "Other"}.get(cat, cat.title())
        lines.append(f"  {_BOLD}{title}{_RESET}")
        for r in items:
            glyph, color = _SEVERITY_STYLE.get(r.severity, ("?", ""))
            msg = f"{color}{r.message}{_RESET}" if color else r.message
            lines.append(f"    {glyph} {msg}")
            if r.fix:
                lines.append(f"        {_DIM}→ {r.fix}{_RESET}")
        lines.append("")

    parts = []
    for sev in ("critical", "warning", "info"):
        if summary.get(sev, 0):
            parts.append(f"{summary[sev]} {sev}")
    if not parts:
        parts.append("all checks ok")
    lines.append(f"  Summary: {', '.join(parts)}")
    lines.append(f"  {_DIM}Run `wiki doctor --json` for machine-readable output.{_RESET}")
    return "\n".join(lines)


# ── JSON renderer ───────────────────────────────────────────────────


def render_json(results: list[CheckResult], summary: dict) -> str:
    payload = {
        "vault": ROOT_DIR.name,
        "engine_revision": _git_revision(),
        "summary": summary,
        "checks": to_json(results),
    }
    return json.dumps(payload, indent=2)


# ── Helpers ─────────────────────────────────────────────────────────


def _git_revision() -> str:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(WIKI_DIR), "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
        )
        return out.decode().strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return "unknown"


def _exit_code(results: list[CheckResult]) -> int:
    return 1 if any(r.severity == "critical" for r in results) else 0


# ── Entry point ─────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Full vault-health audit. Default: pretty report.",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Machine-readable output (for agents).",
    )
    parser.add_argument(
        "--quick", action="store_true",
        help="Skip network + subprocess probes (sub-50ms; for hooks).",
    )
    args = parser.parse_args()

    results = build_health(quick=args.quick)
    summary = health_summary(results)

    if args.json:
        print(render_json(results, summary))
    else:
        print(render_pretty(results, summary))

    return _exit_code(results)


if __name__ == "__main__":
    sys.exit(main())
