---
milestone: M018
slice: S06
project: llm-wiki
created: 2026-05-17T13:00:00Z
status: planned
task_count: 5
completed_tasks: 0
---

# M018-S06 — Slice Plan

**Goal:** M018 closes: all 5 exit criteria green, documentation reflects the new `scripts/compile_stages/` shape, backlog flipped to shipped, memory pointer written. Q1's serial-after-file decision means scheduling-policy is already decided (no work in this slice); this is the regression + closeout slice.

## Tasks

- [ ] T01 -- Run S01 fixture-vault regression test end-to-end against the post-S05 engine. Capture exit code + any diff. Expected: zero diff, exit 0. Document the run + result in `M018-S06-T01-SUMMARY.md`. If diff appears: stop, surface, do NOT rewrite the baseline silently.
- [ ] T02 -- Update `docs/engine-layout.md` to reflect the new `scripts/compile_stages/` package (select.py, compile.py, commit.py, post_passes.py + types.py shared dataclasses). Update AGENTS.md compile-section if any operator-facing surface changed (e.g. `wiki produce` already documented in Phase 1, but the post-pass-lift may have changed something subtler).
- [ ] T03 -- Refresh architecture infographic per `feedback_infographics_track_engine`: `docs/architecture.excalidraw` gets the 3-stage compile breakdown + post-pass orchestrator as an inner-structure detail of the compile.py card. Render to `docs/architecture.png`. Same theme as committed PNG (light mode).
- [ ] T04 -- Flip `.ytstack/backlog/producer-seam.md` Milestone-B section to `status: shipped` with commit refs. Flip `.ytstack/backlog/preflight-guard-rollout.md` to `status: subsumed by M018` (CONTEXT exit-criterion noted it was the natural home). Write memory pointer `~/.claude/projects/.../memory/project_m018_producer_seam_phase2_shipped.md` + entry in MEMORY.md.
- [ ] T05 -- Flip `M018-ROADMAP.md` `status: planned` → `status: done`. Update STATE.md: `current_milestone: none` + status-block summarizing M018 ship. Run `ytstack:reassess-roadmap` to surface next-priority candidate from `.ytstack/backlog/PRIORITY.md`.

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`. M018 ROADMAP `status: done`. Regression vault green. Backlog + docs + memory updated. Architecture diagram refreshed.

## Notes

Q1's lock means this slice does NOT touch scheduling code — that's why the slice is "closeout" not "scheduling decision" despite the placeholder name in the original ROADMAP. If T05's `reassess-roadmap` surfaces an architectural item (e.g. Model seam, dream.py extraction) ready to plan, leave the suggestion in STATE.md but don't auto-plan it.
