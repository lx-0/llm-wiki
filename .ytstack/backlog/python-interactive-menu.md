# Python-driven interactive menu (replace bash home_screen)

**Status:** IMPLEMENTED — `scripts/menu.py` live; bash home_screen code deleted; `prompt_toolkit>=3.0` in pyproject deps; 13 catalog tests green.
**Date:** 2026-05-17

## Problem

The bash home screen (commits `6504ab6` → `acae830` → `1852029` → `dd21549`
→ `1b4ea5e`) has fought a series of bash 3.2 quirks on macOS:

- `${var,,}` lowercase missing → fixed via `tr`
- Empty-array `${arr[@]}` under `set -u` → fixed via `${arr[@]+...}`
- `read -t 0.05` rejected: fractional timeouts need bash 4+ → CURRENT
  blocker that breaks the arrow-key support entirely (raw-mode
  ESC-sequence handling can't time out without fractional `-t`).

Each fix has cost a commit + a session. The pattern is clear: every
new interactive feature (cursor nav, fuzzy filter, color, multi-line
redraw) trips the next bash 3.2 quirk. Plain bash is the wrong tool
for a multi-line scrollable menu; it was the right tool for the
one-shot wizards in `lib/ui.sh` (confirm / ask / select_one).

## Goal

Move the home screen + category browse into a Python script that uses
a real TUI library. Bash stays as the dispatcher for everything else.

Operator-visible behaviour stays identical:

- `wiki` (TTY) → home screen with suggestions / quick actions / browse / `/foo`
- `wiki <subcommand>` → bash, fast (~10ms), scriptable, hook-compatible
- `wiki menu` → home screen even from non-TTY (e.g. nested-script)

What CHANGES is the rendering + key-handling layer, not the surface.

## Architecture

```
wiki (bash entry-point)
  │
  ├── case "$1" in
  │     "")     → if TTY: exec uv run python scripts/menu.py
  │              else:    cmd_help                    (unchanged)
  │     menu)   → exec uv run python scripts/menu.py  (NEW alias target)
  │     compile|flush|lint|query|...                   (unchanged, bash)
  │
  └── lib/ui.sh: confirm / ask / select_one / select_many / pause
       (unchanged — one-shot wizards stay bash, they're fine)

scripts/menu.py (NEW, ~250 LOC)
  │ uses questionary (built on prompt_toolkit) for the picker UX:
  │   - questionary.select() for the suggestion list (real arrow nav)
  │   - questionary.text() for `/foo` filter input
  │   - questionary.confirm() for confirm-on-expensive (deferred)
  │ uses scripts/menu_context.py for the probe (unchanged)
  │ dispatches via subprocess.run([str(WIKI_BIN), <subcommand>, ...])
  │   — re-enters the bash entry-point. No re-implementing cmd_*.

scripts/menu_context.py (unchanged)
  Probe + status one-liner. Already pure Python, already JSON-emitting.
```

## What gets removed from bash

From `wiki`:
- `home_screen` (~40 LOC)
- `home_screen_plain` (~40 LOC)
- `home_render_screen` (~50 LOC)
- `home_render_status` (~25 LOC)
- `home_read_key` (~25 LOC)
- `home_query` (~10 LOC)
- `home_dispatch_suggestion` (~25 LOC)
- `home_fuzzy_filter` (~50 LOC)
- `category_menu` (~110 LOC for 6 buckets)
- `home_correct_add` (~6 LOC)
- `_home_command_catalog` (~50 LOC of heredoc)

Total: ~430 LOC bash deleted.

From `lib/ui.sh`:
- `select_one_keyed` (~45 LOC) — was only used by home_screen, no other
  caller in lib/*.sh or wiki.

Kept in `lib/ui.sh`:
- `confirm`, `ask`, `select_one`, `select_many`, `pause` — still used
  by config wizard, hooks installer, seed prompts. Those are one-shot
  yes/no / single-line prompts where bash is fine.

## What gets added in Python

`scripts/menu.py` (~250 LOC):

```python
"""Interactive home screen for the wiki CLI.

Invoked by the bash entry-point on bare `wiki` (TTY) or `wiki menu`.
Owns the rendering + keystroke handling for the suggestion list, quick
actions, category browse, and fuzzy filter. Dispatches every action by
shelling out to `wiki <subcommand>` — never re-implements cmd_* logic.
"""

import json
import subprocess
import sys
from pathlib import Path

import questionary
from questionary import Choice, Style

sys.path.insert(0, str(Path(__file__).resolve().parent))
from menu_context import build_status, build_suggestions

WIKI_BIN = Path(__file__).resolve().parent.parent.parent / "wiki"


def render_status_line():
    status = build_status()
    parts = []
    if "articles" in status:
        parts.append(f"{status['articles']} articles")
    ...
    print(f"  {' · '.join(parts)}")


def home_loop():
    while True:
        suggestions = build_suggestions()
        render_status_line()
        choices = build_choices(suggestions)
        pick = questionary.select(
            "What now?",
            choices=choices,
            use_arrow_keys=True,
            use_shortcuts=True,    # letter shortcuts inline
        ).ask()
        if pick is None:           # Ctrl-C / Esc
            return
        if pick == "exit":
            return
        if pick == "filter":
            sub = questionary.text("/").ask() or ""
            handle_fuzzy(sub)
        elif pick.startswith("suggest:"):
            dispatch_subprocess(pick.removeprefix("suggest:"))
        elif pick.startswith("category:"):
            category_menu(pick.removeprefix("category:"))
        elif pick.startswith("quick:"):
            dispatch_subprocess(pick.removeprefix("quick:"))


def dispatch_subprocess(cmd_str: str):
    """Run `wiki <cmd_str>` and pause for operator before returning to menu."""
    parts = cmd_str.split()
    subprocess.run([str(WIKI_BIN), *parts])
    input("\nPress Enter to continue ")
```

The hand-curated 49-entry fuzzy catalog moves into a Python dict in
`menu.py` — same content, just better-typed.

## Dependencies

Add to `pyproject.toml`:

```toml
[project.dependencies]
questionary = ">=2.0"   # built on prompt_toolkit; ~10 MB transitive
```

`prompt_toolkit` is the runtime dep (questionary wraps it). It handles
arrows + colors + cursor properly across macOS Terminal, iTerm, tmux,
linux ttys. Battle-tested in pip / poetry / etc.

## Migration

- `wiki update` pulls new bash + new menu.py + runs `uv sync` →
  questionary lands in `<vault>/.wiki/.venv/`. No vault-side migration.
- Operators on existing installs get the new menu automatically next
  time they run `wiki`.
- No new config keys, no migration entries.

## Cold-start cost

- Old bash menu: ~10ms shell startup + ~150ms python probe = ~160ms
  to first paint.
- New python menu: ~200ms python startup (questionary import) + ~150ms
  probe = ~350ms to first paint.

Delta: +190ms. Visible but acceptable for interactive entry-point that
runs once per session (not per keystroke — the menu loop reuses one
Python process).

`wiki compile` / `wiki flush` etc. stay bash, ~10ms, no change.

## Behavioural surface

Identical to current spec:

- ↑ / ↓ arrow nav over suggestions (FINALLY WORKS — no more bash 3.2 fight)
- Enter dispatches highlighted item
- 1-9 jumps to suggestion by number
- q/f/l/s quick actions
- c/i/k/d/a/g category browse
- h help / x exit / Ctrl-C / Ctrl-D
- `/foo` opens fuzzy filter input

Plus questionary gives us for free:

- Live filter as you type in a select (`use_search_filter=True`)
- Coloured selected-item highlight without manual ANSI
- Page-up / page-down for long lists
- Backspace + arrow keys in text inputs

## What stays out (deferred)

- **Migrate `lib/ui.sh` wizards to Python too** — separate arc.
  `confirm`/`ask`/`select_one`/`select_many` work fine in bash for
  one-shot prompts; the pain was the multi-line scrollable menu.
- **`wiki config` interactive editor** — currently bash via lib/config.sh.
  Same logic: it's a one-shot wizard with `select_one` calls, bash is
  fine. Move only if it grows TUI ambitions.
- **Tab-completion for `wiki <subcommand>`** — orthogonal, would need
  shell-specific completion scripts (bash / zsh / fish).
- **Confirm-on-expensive guard before suggestion dispatch** — operator
  rejected this earlier ("execute, don't re-confirm"). Stays out.

## Open questions

1. **Use `questionary` or `prompt_toolkit` directly?** Questionary is
   the higher-level API; prompt_toolkit is more powerful but more code.
   Recommendation: questionary for the picker layer, drop to
   prompt_toolkit only if questionary can't express a needed UI.
2. **Do we delete the bash home_screen code now, or keep both behind
   `features.home_screen_python` flag for one release cycle?** Same
   spirit as `compile_callback_gate` — one-line rollback if questionary
   surfaces a terminal issue we didn't anticipate.
3. **Cold-start optimization: lazy-import questionary?** Save ~80ms by
   deferring `import questionary` until after the probe runs. Probably
   not worth the code mess; mention as backlog.
