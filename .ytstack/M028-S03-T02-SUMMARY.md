---
milestone: M028
slice: S03
task: T02
project: llm-wiki
closed: 2026-06-13T18:20:00+0200
verification: passed
---

# M028-S03-T02 -- Summary

## Commits
- `810270a` -- feat(correct): over-broad-term warning at `correct add` (M028-S03-T02, issue #5)

## Outcome
`wiki correct add` warns when a `negation_term` matches more than
`limits.correct_broad_term_threshold` (default 15) existing articles. New config
knob with migration + config.example in the same commit (hard rule).
`_count_term_matches`/`_warn_broad_terms` live in correct.py (light, no SDK import).
Warn-only, never blocks.

## Deviations from plan
The warn-helper tests were written after the small additive helper (tests-after,
not strict RED-first) — acceptable for a simple grep helper; the migration
round-trip count tests WERE the failing-first guard (92→93 + fixtures).

## Follow-ups
T03 (last S03): acceptance — dry-run + warning together; closes S03 → S04.

## Verification
`uv run pytest -q` → **1350 passed, 1 skipped**.
