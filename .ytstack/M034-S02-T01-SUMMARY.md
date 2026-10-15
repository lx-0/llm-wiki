---
milestone: M034
slice: S02
task: T01
project: llm-wiki
closed: 2026-10-15T20:36:00+02:00
verification: passed
---

# M034-S02-T01 -- Summary

## Commits

- `1dddd19` -- M034-S02-T01: line-based prompt helpers on core/console — confirm, ask, select_one, select_many, pause over a byte-wise read_line; open question 3 decided on measurements
- `7513916` -- M034-S02-T01: planned — line-based prompt helpers on core/console

## Outcome

`core/console` has the Python counterpart of `lib/ui.sh`. All five prompts take `fd=` / `out=`
for tests and default to stdin / stderr.
- **`read_line(fd)`** reads byte by byte up to `\n` (`None` at EOF with nothing read).
- **`confirm`:** `[Y/n]` / `[y/N]`; y/Y/j/J is yes; empty or EOF takes the default.
- **`ask`:** a `[default]` hint, a re-asking validator, and the default at EOF instead of
  looping.
- **`select_one`:** a numbered list with `*` on the default; anything out of range takes the
  default.
- **`select_many`:** space-separated numbers; empty takes the defaults; junk is skipped.
- **`pause`.**

The engine inherits the parity choices from `lib/ui.sh`: the prompt texts and hints, the
markers, and the fall-backs. Two choices deliberately differ:
- **Prompts are on stderr,** `confirm` and `pause` included.
- **EOF never loops.**

No command uses the helpers yet; T02 / T03 wire them in.

Open question 3 is decided (DECISIONS 2026-10-15 "Prompts in Python"), on measurements made
with two answers piped:
- `questionary.confirm` and `prompt_toolkit.prompt` warn `Input is not a terminal`, write a
  terminal redraw into stdout, and consume all remaining stdin;
- `sys.stdin.readline()` reads ahead past the line, so a following child reads nothing.

## Deviations from plan

- **The recommendation's argument was corrected.** It said OSS prompt libraries "would pull
  prompt_toolkit into each vault", but `prompt_toolkit` is a dependency already (`menu.py`).
  The rejection rests on the measured pipe behaviour instead, and the DECISIONS entry and
  M034-CONTEXT say so.
- **One deliberate difference from bash.** Bash colours prompts by stdout's TTY state;
  `core/console`'s `C_*` follow stderr's, where the prompts now go.

## Follow-ups

- **T02 / T03** wire the helpers into `config` / `setup`. Moving `confirm` / `pause` from
  stdout to stderr is the decided difference for those goldens (`setup-wizard`).
- **T03:** `wiki setup`'s hooks step runs `wiki hooks install` as a child that inherits
  stdin. This task's pipe test is the guarantee it gets its own answers.

## Verification

Commands, all passed:
- `uv run --frozen pytest tests/test_console_prompts.py -q`: 27 passed. All were watched
  failing first. With `read_line` swapped for a buffered `readline`, the load-bearing
  pipe-into-a-child test and three others fail.
- `uv run --frozen --group typecheck ty check scripts/core`: clean.
- `uv run --frozen pytest -q`: 2389 passed, 1 skipped.

CI is green on `1dddd19` (ci + secrets-scan; the pipe tests pass on Linux too).
