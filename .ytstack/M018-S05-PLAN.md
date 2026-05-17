---
milestone: M018
slice: S05
project: llm-wiki
created: 2026-05-17T13:00:00Z
status: planned
task_count: 5
completed_tasks: 0
---

# M018-S05 — Slice Plan

**Goal:** `run_post_passes(source_path, compile_result, state) → list[ProducerResult]` lives in `scripts/compile_stages/post_passes.py` and replaces the inline post-pass call site that Phase 1 wired into `compile.py:main()` (commit `e730d26`). After this slice, no producer logic remains inline in `compile.py`.

## Tasks

- [ ] T01 -- Locate the Phase-1 post-pass call site in `compile.py:main()` per-file loop (added by `e730d26`). Extract the block into a new `scripts/compile_stages/post_passes.py:run_post_passes(source_path, compile_result, state) → list[ProducerResult]`. State arg is read-write for `producer_cost_total` accumulation.
- [ ] T02 -- `run_post_passes()` iterates `ProducerRegistry.all()` and calls `evaluate_and_run()` for each — **serial execution** (CONTEXT Q1-locked: serial-after-file is the decided policy). Per-producer errors do NOT block subsequent producers nor state-save (α-contract, also CONTEXT Q1). Cost accumulates into `state["producer_cost_total"]`.
- [ ] T03 -- Add `tests/test_run_post_passes.py` with ≥3 cases: (a) all 3 producers run for a source that matches every gate; (b) a raising producer is caught + reported as `ProducerResult(status="failed")` and subsequent producers still run; (c) a gate-skipped producer returns `status="skipped"` without invoking `run()`. Mock `ProducerRegistry` and individual producers via fixtures.
- [ ] T04 -- Wire `compile.py:main()` per-file loop to call `run_post_passes()` exactly once after `commit_article()` returns ok. The full per-file loop body becomes: `select_sources` (S02) → `compile_source` (S03) → `commit_article` (S04) → `run_post_passes` (S05) → `save_state`. Run S01 regression vault — byte-identical.
- [ ] T05 -- Measure the per-file loop body LOC. Must be <40 LOC per CONTEXT exit-criterion #1. If it overshoots, identify what didn't extract cleanly + decide between (a) one more extraction task here or (b) S06 followup. Document the final count in slice-summary.

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`. `run_post_passes()` independently importable, ≥3 unit tests, regression vault byte-identical, per-file loop body <40 LOC.

## Notes

This slice is what M018 was really for — everything before it was extraction prep. Q1's serial-after-file decision means **no scheduling policy** in this slice (S06 was originally that slot; with Q1 locked, S06 is a closeout slice now). Any temptation to add `defer:` / `fanout:` spec fields here = scope drift; that's a strictly-additive future change when a real producer needs it.
