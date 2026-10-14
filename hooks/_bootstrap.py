"""The one `sys.path` bootstrap of the engine (DECISIONS 2026-10-14, M033-S02).

Claude Code runs the hooks by file path from whatever directory the session lives in
(`uv run --project <vault>/.wiki python <vault>/.wiki/hooks/session-end.py`): Python puts
`hooks/` on `sys.path`, nothing puts `scripts/`. Importing this module first makes
`core.*` resolvable; every other engine process gets `scripts/` from Python itself (a
script run by path), from `core.entry` (a child spawned as `python -m`), or from pytest's
`pythonpath`. Nothing else in the tree touches `sys.path` — `tests/test_layout.py` pins it.
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
