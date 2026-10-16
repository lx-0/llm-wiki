---
milestone: M034
slice: S05
task: T04
project: llm-wiki
closed: 2026-10-16T04:05:00+02:00
verification: passed
---

# M034-S05-T04 -- Summary

## Commits

- `e0251dc` -- M034-S05-T04: one help system — every help text prints through cli_help.print_help (bold title and headers on a terminal, plain in a pipe), by the dispatcher and the five handlers alike; `wiki help <cmd>` prints that command's help instead of dropping the name; guards: no help text left in the bash, none printed past the seam (0.7.30)

The task was planned in `1422224`, T03's summary commit.

## Outcome

Every help text is in `cli_help` and prints through `cli_help.print_help`. On a terminal
that gives a bold title and ALL-CAPS headers; in a pipe it gives plain text.
- **Who prints:** the dispatcher, and the five handlers that print their own (config,
  hooks, skills, seed, update). Before, those five printed unstyled.
- **`wiki help <cmd>`** prints that command's help, and an alias prints its target's. It
  used to print the whole catalogue and drop the name. An unknown name is the dispatcher's
  error, exit 1.
- **The `help` row is kind `builtin`:** no command is the bash's any more.

Two guards in `tests/test_cli.py`:
- no `print(H_…` under `scripts/` outside the seam;
- no heredoc or `help_*` function in `wiki` or `lib/*.sh`.

## Deviations from plan

- **One more test than planned:** seed's help is styled on a terminal. The CHANGELOG claims
  it, so it is measured.
- **The catalogue kind `bash` was renamed `builtin`.** Its only row was `help`, which
  `cli.main` answers, and the docstring had called it bash-dispatched.

## Follow-ups

- **T05:** `lib/common.sh` folds into `wiki`. `install.sh` stops sourcing it, and the cloud
  rule's two copies are held to one table.
- **S06:** "one table behind help and menu" builds on `print_help` and the catalogue.

## Verification

Commands:
- `uv run --frozen pytest tests/test_cli.py tests/test_bash_oracle.py -q -k help`: green.
  The 17 `*-help.txt` records are unchanged, since they are piped.
- **RED first:** the four new tests failed on the pre-T04 tree, run in a scratch worktree
  (`git worktree add`, removed after without `--force`). The bash guard caught `cat <<EOF` in
  `830d776`'s `wiki`.
- `uv run --frozen pytest -q -p no:cacheprovider`: 2645 passed, 1 skipped. ruff and
  `ty check scripts/core`: clean.
- CI on `e0251dc`: both runs green.
