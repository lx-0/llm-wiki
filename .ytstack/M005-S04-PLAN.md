---
milestone: M005
slice: S04
project: llm-wiki
created: 2026-05-15T17:00:00Z
status: planned
task_count: 4
completed_tasks: 1
---

# M005-S04 -- Slice Plan

**Goal:** Compile carries forward unresolved State items, demotes resolved ones to Timeline based on substrate evidence, and preserves manual `- [x]` across re-runs.

## Tasks

- [x] T01 -- Compile-prompt rule -- read existing State Action Items + Open Threads BEFORE rewriting; carry forward unresolved; preserve manual `[x]` state
- [ ] T02 -- Resolution detection -- when next-pass substrate contains semantic resolution evidence ("sent the deck", "Bob made the intro"), the matching State item moves to Timeline with `[resolved]` + citation
- [ ] T03 -- Fixture test -- existing person page with State items + new substrate with resolution evidence → verify demotion to Timeline with citation
- [ ] T04 -- Fixture test -- manual `- [x]` in State Action Items → verify compile preserves it across re-runs

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`. Both fixture tests green; resolution-demotion is conservative (no false demotions on the canary).

## Notes

(Add observations during slice execution. Edge cases not covered here -- orphan items, contradiction between manual `[x]` and substrate resolution -- become entries in `KNOWLEDGE.md` if surfaced.)
