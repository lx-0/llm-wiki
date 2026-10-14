---
milestone: M033
slice: S02
task: T01
project: llm-wiki
closed: 2026-10-14T23:05:00+02:00
verification: passed
---

# M033-S02-T01 -- Summary

## Commits

Committed together with this summary under the `M033-S02-T01:` ref — `git log --grep '^M033-S02-T01'`.

## Outcome

The layout is decided and recorded: **`scripts/` is the engine's source root, not a
package** (`DECISIONS.md` 2026-10-14, M033-CONTEXT open question 3 closed, exit criterion 4
reworded to match, the inventory in the S02 plan's notes). Measured on `466f569`: 82 files
carry a `sys.path.insert` in five shapes; 28 files (75 lines) spell their imports
`scripts.core.*` / `scripts.reports.*` while the rest import `core.*`; with both roots on
the path `core.paths is scripts.core.paths` is **False** — two module objects, the KNOWLEDGE
C01 trap — because the directory has no `__init__.py` and resolves as an implicit namespace
package whenever `.wiki/` is on the path. `runpy.run_module("collectors.cli")` from
`scripts/` runs a sub-package CLI with no bootstrap. Consequences for T02–T05: one import
identity (`core.*`, the 28 files rewritten, a guard test), `cli.py` spawning
`python -m <module>` with `cwd=SCRIPTS_DIR`, bootstraps only in `hooks/` and pytest's
`pythonpath`, the five hyphenated scripts renamed, and **no `scripts/__init__.py`** (it would
reopen the split). Layout B (`scripts` as the package) was costed at ~190 rewritten files
plus every operator hook command, i.e. M034's port pulled forward — rejected.

## Deviations from plan

- The plan's "probe both layouts on a branch of the test suite" became two targeted probes
  plus counts: the identity probe and the `-m` probe answer the question directly; a full
  rewrite under each layout to compare would have been the work itself.
- Exit criterion 4 in M033-CONTEXT was written for layout B ("`scripts/__init__.py` exists",
  "`python -m scripts.<mod>`"); it now states the chosen layout. Recorded in the criterion
  text itself.

## Follow-ups

- T02: rename the five hyphenated scripts and update their call sites (docs, tests, the
  `preprocessors/inbox.py` and `flush.py` comments).
- T03: `cli.py` `_run_child` → `-m`; `core/piggybacks.py` cmd shapes (`collectors/cli.py
  <name>` → `-m collectors.cli <name>`); `core/piggyback_runner.py`'s own spawn.
- T04: the rewrite of the 28 files, the bootstrap removal (82 files), the guard test
  (`no scripts.* import`, `no sys.path.insert outside hooks/ + conftest`, `scripts/__init__.py`
  absent, one module identity), E402 per-file ignores retired.

## Verification

Command: the identity probe (`same object: False` — the baseline T04 flips), `grep -rln
"from scripts\.\|import scripts\." … | wc -l` → 28, the DECISIONS heading and the CONTEXT
"decided 2026-10-14" line present — passed.
