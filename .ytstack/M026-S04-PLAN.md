---
milestone: M026
slice: S04
project: llm-wiki
created: 2026-05-23T15:25:00+0200
status: planned
task_count: 1
completed_tasks: 1
---

# M026-S04 -- Slice Plan

**Goal:** Flip the compile pipeline to a typed `CompileOutcome` return end-to-end and
make `main()` the single state-save site, deleting the `_STATE_MUTATING_SKIPS` leak +
the magic-key dict + dead `_build_owner_block`. Milestone exit criteria met.

## Tasks

- [x] T01 -- CompileOutcome flip + main rewire + cleanup.
  - Handlers return `CompileOutcome`: `_run_index_only`/`_run_health_stub` →
    `status="skipped"`, the same `skip_reason`, `ingest_hash=True`, and they NO LONGER
    write state (main persists). `_run_compile_route` maps compile_source's
    `CompileResult`/chunk-aggregate → `CompileOutcome` (compiled+ingest_hash on success;
    skipped/failed with no ingest on skip/fail/all-chunks-fail).
  - `compile_file` returns `CompileOutcome` (dry_run/Skip → skipped, ingest_hash=False).
  - `main()` loop: `match outcome.status`; skip → count (+ persist iff `ingest_hash`);
    failed → FailureClass(outcome.failure_kind, …) + abort logic; compiled → post-passes
    + persist + total_cost/last_compile. Single `save_state` per outcome.
  - Delete `_STATE_MUTATING_SKIPS` + its reload branch; delete dead `_build_owner_block`.
  - Update tests: `test_compile_file_dispatch` (4 asserts → CompileOutcome);
    `test_compile_reliability` (timeout/kind-unknown/success/health asserts →
    CompileOutcome; the deterministic-stub test asserts `ingest_hash=True` not a
    handler state-write); replace `test_state_mutating_skips_includes_*` with a test of
    the new contract (handlers signal `ingest_hash=True`).

## Done when

T01 `[x]`, verified. `CompileOutcome` is the return type; `_STATE_MUTATING_SKIPS`,
the magic-key dict, and dead `_build_owner_block` are gone; full compile suite green.

## Notes

- Iron rule preserved: main persists ingested-hash immediately after each outcome
  (compiled OR ingest_hash-skip), same per-file cadence as before.
