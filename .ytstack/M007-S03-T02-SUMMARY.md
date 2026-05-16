---
milestone: M007
slice: S03
task: T02
project: llm-wiki
status: done
completed: 2026-05-16T17:40:00Z
---

# M007-S03-T02 -- Summary

## Outcome

4 MOC templates updated with `WHERE compile_role != "final-only"` Dataview clause. pin.py refuses to pin final-only articles.

## Deviations

None.

## Follow-ups

Existing operator vault MOCs need manual update (`wiki seed --force` overwrites + loses operator hand-curation; safer to surface this as a one-time migration note in S03-T05 docs).

## Verification

4 templates verified, pin.py guard verified, 43 regression tests green.

## Commits

- `<this>` — feat(moc): MOC auto-include filters compile_role=final-only
