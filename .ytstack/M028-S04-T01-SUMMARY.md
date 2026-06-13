---
milestone: M028
slice: S04
task: T01
project: llm-wiki
closed: 2026-06-13T18:38:00+0200
verification: passed
---

# M028-S04-T01 -- Summary

## Commits
- `3de0a4d` -- feat(correct): first-class `supersession` status (M028-S04-T01, issue #5)

## Outcome
`supersession` is now a valid fact status (annotate-only, was-true-now-outdated),
distinct from `negation` (possibly-false, the only delete-eligible status).
`_deletion_allowed` returns False for a supersession fact regardless of
`--allow-delete` / `disposition: delete`. `--status` help updated.

## Deviations from plan
None.

## Follow-ups
T02: lint (`check_facts_violations`) must skip already-`status: superseded`
articles — they keep the term in their historical body and would otherwise be
flagged as violations forever.

## Verification
`uv run pytest -q` → **1353 passed, 1 skipped**.
