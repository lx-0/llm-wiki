---
milestone: M028
slice: S02
task: T01
project: llm-wiki
closed: 2026-06-13T17:40:00+0200
verification: passed
---

# M028-S02-T01 -- Summary

## Commits

- `5c0a9c7` -- feat(correct): engine delete executor → .trash (M028-S02-T01, issue #5)

## Outcome

`_execute_deletes(actions, vault, *, allowed)` moves each agent-nominated article
to `.trash/<ts>/` (preserving its vault-relative path — the move IS the backup,
never `unlink`) and `_clear_index_rows` drops its `index.md` row first (resolving
links before the move). Only files under `knowledge/` are eligible; missing or
out-of-scope paths are skipped. Gated by `allowed` — wired `allowed=False` in
`apply()` so S01's deletion-free behaviour holds end to end until S02-T02 flips the
gate. Executed deletes are folded into the divergence accounting so a real+declared
deletion is not flagged.

## Deviations from plan

None. The `deleted` contract + parser already existed (S01-T03/T04, confirmed at
the reassess boundary), so this task was purely the executor + index-row clearing.

## Follow-ups

- T02: the real gate (`--allow-delete` flag + fact `disposition: delete`) +
  threading the real `deletion_allowed` into the prompt render.
- T03: dirty/non-git tree refusal unless `--force`.

## Verification

Command: `uv run pytest tests/test_correct_apply.py -q && uv run pytest -q`
-- passed. 3 tests (allowed→.trash+index-drop / gate-off→noop / outside-knowledge
skipped). Full suite **1339 passed, 1 skipped**.
