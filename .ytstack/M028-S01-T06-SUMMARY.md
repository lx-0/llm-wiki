---
milestone: M028
slice: S01
task: T06
project: llm-wiki
closed: 2026-06-13T17:30:00+0200
verification: passed
---

# M028-S01-T06 -- Summary

## Commits

- `937cecb` -- feat(correct): golden repro + rename-aware divergence (M028-S01-T06, issue #5)

## Outcome

A golden integration test drives the whole sandboxed apply pipeline over a fixture
vault with a mocked SDK: the agent's proposal renames township→fleet with
`deleted: []`, and `apply()` performs the rename engine-side (file moved, wikilink
`[[../projects/fleet]]` rewritten), deletes nothing (the merely-mentioning article
survives), stamps the fact `applied`, and logs no false deletion alarm.

The test surfaced a real T05 bug: an engine rename (`Path.rename`, unstaged) shows
as delete(old)+create(new) in a snapshot or unstaged git tree, which false-fired
`_divergence`. Fixed: `_execute_renames` now returns the list of renames it
actually performed, and `_divergence(actions, delta, executed_renames)` subtracts
those (basename-normalized) before flagging unaccounted-for deletions. The alarm
now fires only when a file vanished that neither a declared deletion nor an engine
rename explains — the true issue-#5 signal.

## Deviations from plan

The plan anticipated the divergence refactor — executed as planned. The unreliable
rename-COUNT check from T05 was dropped (snapshot mode can't see renames). Net test
delta +2 (golden + rename-no-false-warn; the 2 existing divergence tests updated to
the 3-arg signature).

## Follow-ups

- **S01 is complete (6/6).** Next: `/ytstack:reassess-roadmap` at the slice
  boundary, then S02 (safe opt-in deletion executor).
- The full agent behaviour on the live prompt remains unverified pending a gated
  real SDK run — the golden test mocks the SDK. This is the one honest gap; the
  engine half (parse → execute → report) is now real-tested end to end.

## Verification

Command: `uv run pytest tests/test_correct_apply.py -q && uv run pytest -q`
-- passed. Golden + 3 divergence tests + the parser/reporting/sandbox suite. Full
suite **1336 passed, 1 skipped**.
