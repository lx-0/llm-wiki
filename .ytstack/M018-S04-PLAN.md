---
milestone: M018
slice: S04
project: llm-wiki
created: 2026-05-17T13:00:00Z
status: planned
task_count: 5
completed_tasks: 0
---

# M018-S04 — Slice Plan

**Goal:** `run_post_passes(source_path, compile_result, state) → list[ProducerResult]` lives in `scripts/compile_stages/post_passes.py` and replaces the inline post-pass call site that Phase 1 wired into `compile.py:main()` (commit `e730d26`). After this slice, no producer logic remains inline in `compile.py`.

## Tasks

- [ ] T01 -- Locate the Phase-1 post-pass call site in `compile.py:main()` per-file loop (added by `e730d26`). Extract the block into a new `scripts/compile_stages/post_passes.py:run_post_passes(source_path, compile_result, state) → list[ProducerResult]`. State arg is read-write for `producer_cost_total` accumulation.
- [ ] T02 -- `run_post_passes()` iterates `ProducerRegistry.all()` and calls `evaluate_and_run()` for each — **serial execution** (CONTEXT Q1-locked: serial-after-file is the decided policy). Per-producer errors do NOT block subsequent producers nor state-save (α-contract, also CONTEXT Q1). Cost accumulates into `state["producer_cost_total"]`.
- [ ] T03 -- Add `tests/test_run_post_passes.py` with ≥3 cases: (a) all 3 producers run for a source that matches every gate; (b) a raising producer is caught + reported as `ProducerResult(status="failed")` and subsequent producers still run; (c) a gate-skipped producer returns `status="skipped"` without invoking `run()`. Mock `ProducerRegistry` and individual producers via fixtures.
- [ ] T04 -- Wire `compile.py:main()` per-file loop to call `run_post_passes()` exactly once after `commit_article()` returns ok. The full per-file loop body becomes: `select_sources` (S01) → `compile_source` (S02) → `commit_article` (S03) → `run_post_passes` (S04) → `save_state`. Smoke check: `wiki compile` on lxw runs end-to-end, producer output (suggestions/curiosity/takes) still lands.
- [ ] T05 -- Measure the per-file loop body LOC. Must be <40 LOC per CONTEXT exit-criterion #1. If it overshoots, identify what didn't extract cleanly + decide whether to add one more extraction task here. Document the final count in slice-summary. This is also the M018 closeout slice: flip backlog (producer-seam.md → shipped, preflight-guard-rollout.md → subsumed), write memory pointer `project_m018_producer_seam_phase2_shipped.md`, update STATE.md + ROADMAP `status: done`, refresh `docs/engine-layout.md` + `docs/architecture.excalidraw` per `feedback_infographics_track_engine`.

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`. `run_post_passes()` independently importable, ≥3 unit tests, lxw smoke green, per-file loop body <40 LOC, docs + diagram + backlog + memory + STATE flipped.

## Notes

This is the final slice (S05/S06 cancelled). The original S06 closeout work (docs/diagram/backlog/memory/STATE) folds into T05 here. Q1's serial-after-file decision means **no scheduling policy** in this slice — any temptation to add `defer:` / `fanout:` spec fields here = scope drift; that's a strictly-additive future change when a real producer needs it.
