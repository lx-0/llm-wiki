---
milestone: M025
slice: S03
project: llm-wiki
created: 2026-05-23T08:53:30+0200
status: planned
task_count: 4
completed_tasks: 0
---

# M025-S03 -- Slice Plan

**Goal:** The correction write-back closes the loop -- a correction writes a
supersede-marker, and the next normal compile cycle regenerates the affected article
(no instant surgical patch). End-to-end verified on a live vault.

## Tasks

- [ ] T01 -- Eng-seam spike + decision (resolves the M025-CONTEXT open question):
  determine compile's regeneration path -- full-corpus vs per-source-file vs
  agent-side write. Read `scripts/compile.py` + `compile_stages/`. Decide the
  supersede→regenerate mechanism (favour "superseded capture ⇒ re-compile that
  source file" if compile is per-source). Write the finding + decision into
  `M025-CONTEXT.md`. If the seam is bigger than M, that is the L split-signal --
  flag it before T02.
- [ ] T02 -- Supersede-marker: a `kind: correction` capture marks the original
  capture's interpretation superseded in `state/capture_index.json` (status
  `superseded`, record correction text + link correction→original). Python-side,
  deterministic. Unit tests: marker written, idempotent, links resolve both ways.
- [ ] T03 -- compile honours the supersede-marker → regenerates the affected
  article on the next normal compile cycle via the mechanism chosen in T01. No
  instant single-item surgical patch (scope guard). Tests at the chosen seam (SDK
  boundary mocked where the agent-side write is involved; the trigger/selection
  logic tested deterministically).
- [ ] T04 -- E2E live smoke (lxw or sidney vault, per REGEL #1): drop a capture →
  observe wrong reading in the digest → drop a correction by ID → run one compile
  cycle → assert the article is corrected and the old reading is gone. Record spend
  + one observation. No mock.

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`. Milestone exit
criteria (M025-CONTEXT) all green, especially the E2E one.

## Notes

- T01 is an investigation task by design -- it resolves the load-bearing eng-seam
  before any compile code is written. Honest TDD applies once the mechanism is known.
- Watch the M018 lesson: knowledge/ writes are agent-side via SDK tool-use, so
  "regenerate" must ride the existing agent-write path, not a new Python file-patch.
  This is exactly why the surgical instant-patch was cut in CEO review.
