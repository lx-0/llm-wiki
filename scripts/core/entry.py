"""How one engine process spawns another — the single place that knows the layout.

`scripts/` is the engine's source root, not a package (DECISIONS 2026-10-14): every
module imports `core.*`, `collectors.*`, … with `scripts/` on `sys.path`. A child is
therefore started as `python -m <module>` with `scripts/` first on its PYTHONPATH —
sub-package entry points (`collectors.cli`, `core.piggyback_runner`, …) need no
`sys.path` bootstrap of their own, and the caller's working directory is inherited so
relative arguments keep resolving against the operator's cwd.

Consumers: `cli.py` (every `wiki <command>` handler), `core/piggybacks.py` (runner +
task), `flush.py` (compile + dashboard children), the preprocessors' compile trigger.
The bash layer (`wiki`, `lib/*.sh`) spells the same thing as
`PYTHONPATH="$WIKI_DIR/scripts" uv run … python -m <module>` until M034 ports it.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent  # core/ → scripts/


def module_for(handler: str) -> str:
    """`preprocessors/inbox.py` → `preprocessors.inbox`: a handler path relative to
    `scripts/` as the module name `python -m` runs it under."""
    if not handler.endswith(".py"):
        raise ValueError(f"handler must be a .py path relative to scripts/: {handler!r}")
    return handler[:-3].replace("/", ".")


def child_env(base: Mapping[str, str] | None = None) -> dict[str, str]:
    """A copy of ``base`` (default: the live environment) with `scripts/` first on
    PYTHONPATH; an inherited PYTHONPATH is kept behind it, never replaced."""
    env = dict(os.environ if base is None else base)
    inherited = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(SCRIPTS_DIR) + (os.pathsep + inherited if inherited else "")
    return env


def python_m(handler: str, *args: str) -> list[str]:
    """The argv that runs ``handler`` as a module in this interpreter."""
    return [sys.executable, "-m", module_for(handler), *args]
