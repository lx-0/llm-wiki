---
milestone: M007
slice: S01
task: T03
project: llm-wiki
status: done
completed: 2026-05-16T16:00:00Z
---

# M007-S01-T03 -- Summary

## Outcome

Added `check_compile_role` to `scripts/lint.py` (~30 LOC + CHECKS list entry):
- Walks every `.md` under `raw/`, `daily/`, `knowledge/`, `inbox/`
- For files with `compile_role:` frontmatter, validates against `VALID_ROLES` (imported from `scripts.core.compile_role`)
- Emits `severity=error, code=compile_role_invalid` with the bad value + list of allowed values
- Files without `compile_role:` get no issue (default-by-location inference handles them at compile time)

## Deviations from plan

**Cross-location-move warning deferred.** Slice plan mentioned "warns when a file moved location-class without explicit override". That requires git-history walking (`git log --follow --diff-filter=R`) to identify renames across top-level boundaries — not load-bearing for shipping the axis, and out of scope for one-context-window T03. Tracked as a follow-up; can be added later as `check_compile_role_drift` if real demand surfaces.

## Follow-ups

- **T04** (next): pytest formalization with synthetic fixtures (vault-like dir with valid + invalid + missing `compile_role:` frontmatters). Should cover the `check_compile_role()` output dicts directly, not just standalone enum logic.
- Possible follow-up: cross-location-move warning if any real operator gets bitten by silent inference flipping after a file rename.

## Verification

`uv run python scripts/lint.py --structural-only` registers the new check, runs without crashing, returns 0 issues against current vault (no `compile_role:` frontmatter exists yet — empty result is correct).

Enum logic standalone confirmed: 5 invalid values rejected (`'bogus'`, `'final'`, `'source'`, `''`, `'SOURCE-ONLY'`), 3 valid values accepted.

## Commits

- `2ea0338` — feat(lint): check_compile_role enum validation — M007-S01-T03
