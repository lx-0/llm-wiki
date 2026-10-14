---
milestone: M032
slice: S04
project: llm-wiki
created: 2026-10-14T13:40:00+02:00
status: planned
task_count: 4
completed_tasks: 2
---

# M032-S04 -- Slice Plan

**Goal:** The menubar panel is rebuilt as a Svelte app that fits in 640 px at rest with zero paragraphs: labeled navigation, a status strip of three glyph tiles, one Next-up action list with row-level progress and persistent results, Recent, and a collapsed footer — the old renderer is gone.

## Tasks

- [x] T01 -- Panel shell: `src/windows/panel/` Svelte mount from `index.html`; header (brand, vault pill, labeled nav Overview · Notes · Inbox ⟨n⟩ · Settings), Ask bar + answer card (markdown + wikilink chips, copy/clear), auto-fit via `ResizeObserver` kept, nav-hint removed; visibility-driven polling preserved.
- [x] T02 -- Status strip: Library tile (count + 14-day adds sparkline from `vault.list()` mtimes), Health tile (ring: ok / amber / red + count from doctor), Capture tile (channel level meter + state word from listener status, Start/Stop); inline expand per tile; pure derivation functions with vitest coverage.
- [ ] T03 -- Next-up + Recent + footer: action list from `mergeActions` (≤ 5 rows, verb buttons, row progress bar from `onRunProgress`, persistent result pill from `onRunDone` with detail popover), Recent list (type badge + edge), footer with collapsed `+ Add link`, Sources sheet (monochrome icons, Sync / Sync all), Quit.
- [ ] T04 -- Swap + gate: `renderer.ts`, `lib/pending.ts`, `friendlyHealth` and the panel CSS blocks deleted; harness panel states (fresh / asked / running / failed / no-access / empty) light + dark; requested height asserted ≤ 640 in the fresh state; zoom-crop review.

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`.

## Notes

(Add observations during slice execution. Issues that surface become entries in `DECISIONS.md` or `KNOWLEDGE.md`.)
