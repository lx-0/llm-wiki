---
milestone: M005
slice: S01
project: llm-wiki
created: 2026-05-15T17:00:00Z
status: planned
task_count: 4
completed_tasks: 1
---

# M005-S01 -- Slice Plan

**Goal:** Add type-conditional two-layer rendering to `compile.py` for `type: person|project` pages, with a hand-migrated canary that locks the spec.

## Tasks

- [x] T01 -- Define two-layer schema rules in `prompts/compile_main.md` (type-conditional emit of `## State`, `## Action Items`, `## Open Threads`, `## See also`, `---`, `## Timeline` for `person|project`)
- [ ] T02 -- Update `AGENTS.md` schema doc + `templates/` skeleton with an example two-layer entity page
- [ ] T03 -- Hand-migrate one existing `knowledge/people/<slug>.md` to the two-layer shape as canary
- [ ] T04 -- Compile-smoke-test -- run compile.py on a small substrate, verify fresh person-page emits two-layer shape

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`.

## Notes

(Add observations during slice execution. Issues that surface become entries in `DECISIONS.md` or `KNOWLEDGE.md`.)
