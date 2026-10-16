---
milestone: M034
slice: S05
task: T03
project: llm-wiki
closed: 2026-10-16T03:45:00+02:00
verification: passed
---

# M034-S05-T03 -- Summary

## Commits

- `c3bd40a` -- M034-S05-T03: all of `wiki update` runs in Python — phase 1 (help anywhere, the not-a-checkout and dirty-tree guards, the stash offered on a terminal, the --ff-only pull, the clean-only re-apply, the execv of the pulled entry) joins phase 2 in scripts/update_cli.py, held to the 14 records unchanged, four through a pty; cmd_update and lib/ui.sh deleted, `wiki` is 113 lines of bootstrap (0.7.29)

The task was planned in `fa201c9`, T02's summary commit.

## Outcome

All of `wiki update` is `scripts/update_cli.py` now.
- **The pull:** the not-a-checkout guard, and the dirty-tree guard, which refuses without a
  terminal and offers the stash on one (the prompt on stdout, as the bash had it). Then the
  `--ff-only` pull, with the stash popped back if it fails.
- **The hand-over:** after a clean-only re-apply, `_handover` flushes and `execv`s the pulled
  engine's `wiki update --post-pull <rev>`.
- **Help** is answered anywhere in the flags.

`cmd_update` and `lib/ui.sh` are deleted. `wiki` has no command of its own: it is 113 lines
of bootstrap, and `lib/` holds only `common.sh`. All 14 records pass unchanged, the four
stash cases typed through a pty among them.

On scratch, two hops:
- the real 0.7.3 tree (`ee690a0`) updated to `c3bd40a` through its bash and landed in the
  Python phase 2. Its uv log shows two syncs and no `uv run`.
- `c3bd40a` updated to one commit ahead through the Python phase 1: it pulled, `execv`'d
  the pulled entry, and ran phase 2. A hand edit without a terminal was then refused, with
  nothing touched and no stash.

## Deviations from plan

- **The RED came from the switch itself.** The plan's RED drove `python -m update_cli`
  directly. Instead the re-exec test moved to the real entry on an engine copy first, and
  passed against the bash phase 1 as a characterisation. Then the bootstrap switch made it,
  and the help-anywhere test, fail ("the pull runs from the `wiki` entry", "unknown flag:
  --help"). Phase 1 made both pass.
- **`wiki` is already at 113 lines.** That is the ≤ 150 of exit criterion 1, ahead of T05,
  which still folds `lib/common.sh` into it and pins the budget with a test.
- **Phase 1's messages carry resolved paths too** (`/private/tmp` on scratch), as T02 noted
  for phase 2.

## Follow-ups

- **T04 (one help system):** no bash help text is left in `wiki`; the help is `cli_help`'s.
  What remains is making `wiki help` and `wiki <cmd> -h` render from one place, pinned by a
  test.
- **T05:** `lib/common.sh` goes into the bootstrap (`wiki_venv_dir`, `sync_hint`,
  `shell_quote`, the output helpers `_dispatch_python` still uses). A test pins the budget.
  The cloud rule's two copies are held to one table, and install.sh is re-checked.
- **Backlog unchanged:** `update-hooks-hint-only-when-stale.md`.

## Verification

Commands:
- `uv run --frozen pytest tests/test_bash_oracle.py -q -k update`: 20 passed, with the 14
  records unchanged.
- `uv run --frozen pytest tests/test_wiki_update.py -q`: 6 passed. Before the switch they
  passed against the bash phase 1. After the switch 2 failed. After the port all 6 passed.
- `uv run --frozen pytest -q -p no:cacheprovider`: 2640 passed, 1 skipped.
- ruff, ruff format, and `ty check scripts/core` + `scripts/update_cli.py`: clean.
- Scratch: `/tmp/m034-scratch-update.sh` (0.7.3 → `c3bd40a`) and
  `/tmp/m034-scratch-update-hop2.sh` (`c3bd40a` → one ahead), both exit 0.
- CI on `c3bd40a`: both runs green.
