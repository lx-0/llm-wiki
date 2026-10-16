---
milestone: M034
slice: S06
task: T02
project: llm-wiki
closed: 2026-10-16T05:25:00+02:00
verification: passed
---

# M034-S06-T02 -- Summary

## Commits

- `4f4e745` -- M034-S06-T02 (fix): tests/test_output_seam.py formatted — 1c238cd failed CI's `ruff format --check` on tests/, which the local run had checked only for scripts/
- `1c238cd` -- M034-S06-T02: one output path — command modules write through core.console (`say`, print's contract, beside ok/warn/info/fail/print_error); the 391 print( calls in 36 of the catalogue's 47 handler modules are converted, and an AST gate refuses a new one (allowlist with reasons, empty)

The task was planned in `b2df307`, T01's summary commit.

## Outcome

Exit criterion 5 is met: command output goes through `core/console`.
- **`say`:** `core.console.say` takes print's contract (stdout unless `file` names another
  stream, judged at call time). It is the plain-output sibling of `ok` / `warn` / `info` /
  `fail` / `print_error`, and the seam where later behaviour (a quiet mode, a payload-only
  guard) goes.
- **The conversion:** all 391 `print(` calls in 36 of the catalogue's 47 handler and
  subroute modules now call `say`.
- **The gate:** `tests/test_output_seam.py` walks those modules' syntax trees and refuses a
  `print(...)` call outside `ALLOWED` (path → reason). The allowlist is empty, so the count
  went 391 → 0.

No output byte changed: every bash oracle record and payload golden passes, so there was
no release.

## Deviations from plan

- **36 modules, not 25.** The plan counted from a top-25 listing. The full count was 36
  modules with 391 calls, the number the plan stated.
- **The allowlist stayed empty.** The plan expected the JSON payload writers and the TUI
  frame writer on it, but with `say`'s print contract none needs `print` itself.
- **`hooks_cli`'s `core.console` import became a parenthesised block** with `say` added,
  because the line passed the formatter's width.

## Follow-ups

- **T03:** the collector registry and the one collect verb (exit criterion 6), with
  PROCESS.md's bare `uv run --project .wiki` lines.
- **Outside the gate:** modules the commands import (collectors, adapters, reports) still
  print in places. The exit criterion names command modules, which is what the gate holds.
  A wider sweep is not planned.

## Verification

Commands:
- `uv run --frozen pytest tests/test_output_seam.py -q`: RED first (391 calls, `say`
  missing), then 3 passed.
- **The diff:** 391 lines with `print(` removed against 391 with `say(` added, plus `say`'s
  `def`; only imports otherwise. ruff format re-joined 4 files.
- `uv run --frozen pytest -q -p no:cacheprovider`: 2663 passed, 1 skipped. ruff and
  `ty check scripts/core`: clean.
- CI on `1c238cd`: **red** on `ruff format --check`. The new test file was unformatted,
  because the local run had formatted `scripts/` but not `tests/`. Fixed in `4f4e745`. From
  here a local script runs the CI's exact gates before a push: ruff check and format
  `--check` over `scripts hooks tests`, plus `ty check scripts/core`.
- CI on `4f4e745`: both runs green.
