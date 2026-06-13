---
milestone: M028
slice: S02
task: T02
project: llm-wiki
closed: 2026-06-13T17:48:00+0200
verification: passed
---

# M028-S02-T02 -- Summary

## Commits

- `5b0a60a` -- feat(correct): deletion gate — --allow-delete + disposition (M028-S02-T02, issue #5)

## Outcome

Deletion is now operator-gated. `_deletion_allowed(fm, flag)` opens the gate when
either the `--allow-delete` CLI flag is set (per-run) or the fact carries
`disposition: delete` (per-fact, for facts marking factually-false content);
default both absent → False → supersede only. `apply(slug, dry_run,
allow_delete=False)` computes it, threads `"true"/"false"` into the prompt's
`${deletion_allowed}` (replacing S01's hardcoded "false"), and gates
`_execute_deletes`. `main()` exposes `--allow-delete`.

## Deviations from plan

None. The integration test asserts the gate reaches the prompt (`Deletion
permitted: true`) and that a nominated factually-false article ends up in `.trash`.

## Follow-ups

- T03 (next): refuse a deletion-enabled run on a dirty/non-git tree unless
  `--force` — the clean-tree precondition is what makes `.trash` recovery
  trustworthy.

## Verification

Command: `uv run pytest tests/test_correct_apply.py -q && uv run pytest -q`
-- passed. Gate-resolution unit test + end-to-end trash-with-gate-on. Full suite
**1341 passed, 1 skipped**.
