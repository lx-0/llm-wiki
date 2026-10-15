"""M033-S04-T01 — the function-length gate (exit criterion 6).

`scripts/` has no function of `LIMIT` lines or more except the ones in `ALLOWLIST`, each
with the length measured when it was listed; the list can only shrink — an entry whose
function no longer exists, is under the limit, or grew past its recorded length fails
until the entry is fixed. Measured with `ast`: `end_lineno - lineno + 1` (decorators
excluded), methods keyed `Class.method`, nested functions included.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"
LIMIT = 150

# Excluded by path, with the reason beside it.
EXCLUDED = {
    "scripts/core/config_schema.py": (
        "the generated-table module: 72 % comment by design, formatted by hand, read as "
        "TEXT by the config-docs generator (pyproject `format.exclude`)"
    ),
}

# `<path>::<qualname>` → the length measured when the entry was listed. Shrinks only: every
# S04 task that splits a function removes its entry here.
ALLOWLIST: dict[str, int] = {
    # measured 2026-10-15 (M033-S04-T01): 20 of 1,402 functions; T02 removed dream's two,
    # T03 the compile path's three, T04 run_sdk_query, T05 the two collector loops,
    # T06 the two curiosity passes, the takes + intents producers
    "scripts/query.py::main": 253,
    "scripts/reports/_engine/lib/render_summary.py::render_summary": 234,
    "scripts/study.py::cmd_run": 218,
    "scripts/reports/_engine/runner.py::run_inference": 174,
    "scripts/reports/_engine/runner.py::_persist_report": 174,
    "scripts/suggestions/cli.py::main": 169,
    "scripts/core/health.py::check_piggyback_health": 166,
    "scripts/health.py::render": 165,
}


def _lengths() -> dict[str, int]:
    """Every function under scripts/ (methods as Class.method, nested included) → length."""
    out: dict[str, int] = {}

    def walk(node: ast.AST, stack: list[str], rel: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                name = ".".join([*stack, child.name])
                out[f"{rel}::{name}"] = child.end_lineno - child.lineno + 1
                walk(child, [*stack, child.name], rel)
            elif isinstance(child, ast.ClassDef):
                walk(child, [*stack, child.name], rel)
            else:
                walk(child, stack, rel)

    for path in sorted(SCRIPTS.rglob("*.py")):
        rel = str(path.relative_to(REPO))
        if rel in EXCLUDED:
            continue
        walk(ast.parse(path.read_text(encoding="utf-8")), [], rel)
    return out


def test_no_function_at_or_over_the_limit_outside_the_allowlist() -> None:
    lengths = _lengths()
    offenders = sorted(
        ((n, key) for key, n in lengths.items() if n >= LIMIT and key not in ALLOWLIST),
        reverse=True,
    )
    assert offenders == [], f"functions ≥ {LIMIT} lines not in ALLOWLIST (split them):\n" + (
        "\n".join(f"  {n:4d}  {key}" for n, key in offenders)
    )


def test_the_allowlist_only_shrinks() -> None:
    """An entry is the measured length of a function that still needs splitting. Gone,
    under the limit, or grown → the entry must leave the list (or the growth be undone)."""
    lengths = _lengths()
    stale: list[str] = []
    for key, recorded in ALLOWLIST.items():
        actual = lengths.get(key)
        if actual is None:
            stale.append(f"{key}: no longer exists — remove the entry")
        elif actual < LIMIT:
            stale.append(f"{key}: {actual} lines, under the limit — remove the entry")
        elif actual > recorded:
            stale.append(f"{key}: grew {recorded} → {actual} lines — the list only shrinks")
    assert stale == [], "stale ALLOWLIST entries:\n" + "\n".join(f"  {s}" for s in stale)
