---
milestone: M028
slice: S04
task: T02
project: llm-wiki
closed: 2026-06-13T18:46:00+0200
verification: passed
---

# M028-S04-T02 -- Summary

## Commits
- `24e8e75` -- feat(lint): don't re-flag superseded articles as fact-violations (M028-S04-T02, issue #5)

## Outcome
`check_facts_violations` no longer reports an article that is already annotated
`status: superseded` by the fact in question — the annotation is the resolution, and
the historical body legitimately keeps the term. `_superseded_by_fact(art_fm, slug)`
gates the per-(article,fact) pair; an article superseded by a different fact still
violates this one. Without this, the supersede-default would lint-noise forever.

## Deviations from plan
Tested the pure helper rather than the whole `check_facts_violations` (which walks
`WIKI_SUBDIRS` globals — heavy to fixture); the wiring is a one-line `continue`.

## Follow-ups
T03: docs (AGENTS.md, PROCESS.md, config reference, CHANGELOG + version bump,
DECISIONS, KNOWLEDGE). T04: closeout + issue #5 close (gated).

## Verification
`uv run pytest -q` → **1356 passed, 1 skipped**.
