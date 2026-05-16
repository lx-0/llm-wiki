---
milestone: M007
slice: S03
task: T01
project: llm-wiki
status: done
completed: 2026-05-16T17:30:00Z
---

# M007-S03-T01 -- Summary

## Outcome

dashboard_stats.py: `_is_final_only(path)` helper + filter applied to `articles_total` count + `_open_action_items_in_entities` entity loop. New stat `articles_final_only` exposes archived count. Pattern replaces all archives-flag thinking — `compile_role: final-only` is the single knob.

## Deviations from plan

None.

## Follow-ups

T02: MOC auto-include filter (same logic, different surface — scripts/pin.py or wherever MOCs aggregate).

## Verification

- `compute_stats()` returns `articles_final_only` key
- `_is_final_only(Path('/nonexistent'))` → False (handles missing)
- 51 tests green: compile_role + compile_lock + areas-bucket + compile_reliability + author_attribution

## Commits

- `<this>` — feat(dashboard): filter compile_role=final-only from active surfaces
