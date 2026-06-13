---
milestone: M028
slice: S03
task: T01
project: llm-wiki
closed: 2026-06-13T18:12:00+0200
verification: passed
---

# M028-S03-T01 -- Summary

## Commits
- `2ca4a44` -- feat(correct): informative --dry-run blast radius (M028-S03-T01, issue #5)

## Outcome
`--dry-run` now shows the blast radius. `_scan_candidates(terms, roots)` reads each
knowledge/+daily/ `.md` once and classifies a hit as "supersede (delete-eligible)"
when the term is in the H1/slug, else "edit". The dry-run block lists candidates +
per-file action + the deletion-gate state, no agent spawned.

## Deviations from plan
The title-vs-body heuristic first used `text[:200]`, which a short file's body
defeated — the test caught it; switched to H1-line + slug only.

## Follow-ups
T02: over-broad-term warning at `correct add` time (+ config knob + migration).

## Verification
`uv run pytest -q` → **1348 passed, 1 skipped**.
