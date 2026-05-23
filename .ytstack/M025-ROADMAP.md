---
milestone: M025
project: llm-wiki
size: M
created: 2026-05-23T08:42:54+0200
status: in-progress
total_slices: 3
completed_slices: 1
---

# M025 Roadmap

**Goal:** An operator can see how the brain interpreted each cryptic quick-capture
and overturn a wrong reading by capture-ID; the brain marks the old interpretation
superseded and regenerates the affected article on its next compile cycle.

**Exit criteria:**
- Capture lands in `raw/` with a stable capture-ID; ID survives into `compiled_from`.
- `daily-digest` shows recent captures keyed by ID with interpretation + added context.
- A capture line referencing a known ID is recognized as a correction → writes a
  supersede-marker.
- E2E: wrong reading → correction by ID → corrected article after one compile cycle.
- Scope guard: no instant single-item surgical-patch primitive.

## Slices

Slice detail lives in per-slice `M025-S##-PLAN.md` files, created by
`ytstack:slice-milestone`. Suggested framing (refine in slice-milestone):

- [x] S01 -- Capture spine: collector + stable capture-ID + capture index (3 tasks)
- [ ] S02 -- Observable loop: capture→article resolution + digest section + correction recognition (3 tasks)
- [ ] S03 -- Correction write-back: supersede-marker + compile regenerate, E2E (4 tasks)

## Run order

Slices execute sequentially. After each slice, `ytstack:reassess-roadmap` checks if
the plan still fits reality. S03 carries the open eng-seam (compile regeneration
path) -- resolve it during S03 slicing; if it explodes, that is the L split-signal.

## How to update this file

- Flip slice checkbox `[ ]` → `[x]` when its tasks are all `summarize-task`-confirmed
- Update `completed_slices` count
- On milestone completion, flip `status: planned` → `status: done` and update global ROADMAP.md
