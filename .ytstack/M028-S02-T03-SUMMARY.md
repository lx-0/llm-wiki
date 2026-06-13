---
milestone: M028
slice: S02
task: T03
project: llm-wiki
closed: 2026-06-13T17:56:00+0200
verification: passed
---

# M028-S02-T03 -- Summary

## Commits

- `033eebd` -- feat(correct): dirty/non-git tree guard for deletion runs (M028-S02-T03, issue #5)

## Outcome

`_tree_safe_for_deletion(vault)` refuses a deletion-enabled run unless the vault
is a git repo with no uncommitted `knowledge/` changes (`knowledge/facts/`
excluded — the just-added fact is expected uncommitted). `apply()` aborts with
rc 3 BEFORE spawning the agent when `deletion_allowed and not force` on an unsafe
tree; `--force` bypasses. A clean git tree is the precondition that makes `.trash`
+ `git restore` recovery trustworthy.

## Deviations from plan

The full-suite run empirically confirmed the guard: the T02 non-git integration
test started failing (deletion now refused) and was updated to opt into `--force`.
That regression IS the proof the guard bites.

## Follow-ups

- T04 (last in S02): consolidated tests + confirm `_divergence` stays silent for a
  declared+executed deletion (already covered piecemeal; T04 pins it as one slice
  acceptance).

## Verification

Command: `uv run pytest tests/test_correct_apply.py -q && uv run pytest -q`
-- passed. non-git→unsafe / clean→safe / dirty-article→unsafe (real git fixture) /
apply refuses rc 3 + no agent spawn / --force bypasses. Full suite **1344 passed,
1 skipped**.
