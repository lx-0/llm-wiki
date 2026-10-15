---
milestone: M034
slice: S03
task: T03
project: llm-wiki
closed: 2026-10-15T23:35:00+02:00
verification: passed
---

# M034-S03-T03 -- Summary

## Commits

- `681b53e` -- M034-S03-T03: core/backup.py — the engine's one backup helper; a second backup in the same second no longer replaces the first (release 0.7.17)
- `49c45f7` -- M034-S03-T03: planned — one backup helper (core/backup.py, 0.7.17)

## Outcome

`scripts/core/backup.py` is the engine's one backup-before-write helper (engine 0.7.17):
- `stamp()`;
- `backup_path(directory, stem, ext)`, the first free `<stem><stamp>[-n]<ext>`;
- `backup(path)`, the `<name>.bak.<stamp>[-n]` sibling copy, the same form as the bash's
  `backup_file`.

Two backups in one second keep both. All five former writers go through it and keep their
file names: correct, take, correct_apply, dedup, the Thunderbird and All-Inkl mail
adapters, and the CLAUDE.md optimizer. `core/frontmatter.backup` is gone. A seam guard keeps
the backup stamp in one place.

## Deviations from plan

- **A wiring test for the two reachable writers.** Thunderbird and All-Inkl run with the
  stamp pinned: the names keep their old shape, and both backups survive. It covers the
  plan's "names unchanged" check as a test instead of a grep.
- **`correct.py` and `take.py` keep their one-line `_backup` delegates** (dedup imports
  `facts.correct._backup`), now pointing at `core.backup`.

## Follow-ups

- **S03-T04 (the port)** backs up agent configs with `core.backup.backup`. Its names are the
  bash's (`<cfg>.bak.<stamp>`, `-2` on a clash), so the hooks goldens hold.

## Verification

Command: `uv run --frozen pytest tests/test_backup.py tests/test_frontmatter.py
tests/test_s02_adapters.py -q` — passed, as did the callers' suites (201 passed). Full
suite: 2469 passed, 1 skipped. `ty check scripts/core` is clean.

Seen RED:
- the module was missing;
- the guard failed on the six sites before they moved (five writers plus correct_apply's
  trash stamp).

CI green on `681b53e`.
