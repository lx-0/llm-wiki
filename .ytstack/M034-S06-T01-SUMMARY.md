---
milestone: M034
slice: S06
task: T01
project: llm-wiki
closed: 2026-10-16T04:55:00+02:00
verification: passed
---

# M034-S06-T01 -- Summary

## Commits

- `51042a1` -- M034-S06-T01: one table behind `wiki help` and the home menu — each catalogue command carries its own menu entries (MenuItem), the TUI derives its categories (the help's groups, keys v g i k d r), shortcut row and fuzzy list from them; the hand-curated lists and core/actions' stale BASH_OWNED_COMMANDS are gone; the dead flush entry leaves the menu (0.7.32)

The task was planned in this commit too: the plan went with S05's close, `5423c8c`, as STATE.

## Outcome

Exit criterion 4 is met: one table behind `wiki help` and the home menu.
- **The entries live on the commands.** Each catalogue command carries its menu entries
  (`MenuItem`: label, hint, args, a prompt or a special handler, an optional shortcut key).
- **The TUI derives everything it browses** from them: one category per help group with
  entries (`MENU_GROUPS`, keys `v g i k d r`), the shortcut row (`QUICK_KEYS` order), the
  fuzzy list, the browse rows and the category keys.
- **The hand-curated lists are gone.** A test refuses any catalogue label or hint spelled in
  `menu.py`.
- **Every entry's argv starts with its own command,** so the menu cannot offer what the
  dispatcher refuses.

`core/actions`' rows, the GUI's pending work, are held to the catalogue alone: the stale
`BASH_OWNED_COMMANDS` union is gone, and a planted bad argv is caught. The non-TTY fallback
and `[h]` print `render_help()` in-process instead of spawning `wiki help`. The
`menu-no-tty` record is unchanged.

## Deviations from plan

- **The flush entry and its `f` shortcut left the menu.** This was a defect found while
  moving the entries. Bare `wiki flush` prints its usage with exit 2 (it needs a hook's
  context file), so the entry has been dead since `1dbb8af` (2026-10-09). The decision is
  in DECISIONS and the CHANGELOG.
- **"Compile all sources" got a browse entry** next to its `C` shortcut. Under the derived
  model a shortcut is an entry with a key, so it now has a category.
- **The category header and browse row use the help's group name in lower case**
  (`collect & ingest`), not the old TUI labels.

## Follow-ups

- **T02:** the print gate (exit criterion 5).
- **For the operator:** the menu's letters changed (0.7.32): `o`/`i` → `i`, `a` → `r`,
  and status/version under `v`.

## Verification

Commands:
- `uv run --frozen pytest tests/test_menu.py tests/test_actions.py tests/test_cli.py tests/test_oracle_payloads.py -q`:
  105 passed.
  - RED first: 5 failed before the catalogue had `MenuItem`.
  - The oracle's menu and help records: 20 passed.
- The home screen rendered to text shows the six categories, their keys and the shortcut
  row.
- `uv run --frozen pytest -q -p no:cacheprovider`: 2660 passed, 1 skipped. ruff and
  `ty check scripts/core`: clean.
- CI on `51042a1`: both runs green.
