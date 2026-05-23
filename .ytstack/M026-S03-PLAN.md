---
milestone: M026
slice: S03
project: llm-wiki
created: 2026-05-23T15:05:00+0200
status: planned
task_count: 1
completed_tasks: 1
---

# M026-S03 -- Slice Plan

**Goal:** Make `compile_file` pure dispatch by extracting its three execution arms
into named module-level functions. Behavior identical; still returns the legacy dict
(the `CompileOutcome` flip is S04, where `main()` changes with it).

## Refinement vs design doc

Handlers stay **in `compile.py`** as module-level functions (`_run_index_only`,
`_run_health_stub`, `_run_compile_route`), NOT a separate `compile_stages/execute.py`.
They use compile.py's I/O constants (`ROOT_DIR`, `INDEX_FILE`, `KNOWLEDGE_DIR`,
`load_state`/`save_state`/`file_hash`); co-locating keeps them next to those deps and
avoids a second round of test-monkeypatch churn (tests patch `compile.*`). The
deepening goal — `compile_file` = thin dispatch, execution in separately-readable
functions — is met either way.

## Tasks

- [x] T01 -- Extract `_run_index_only(source, rel_path, route)`,
  `_run_health_stub(source, rel_path)`, and `async _run_compile_route(source, content,
  rel_path, route)` from `compile_file`'s match arms (verbatim bodies). `compile_file`
  becomes: `route = decide_route(...)`; Skip logging inline; else dispatch to the three
  handlers. Same dict returns, same behavior. Characterization + reliability suites
  stay green unchanged.

## Done when

T01 `[x]`, verified. `compile_file` body is dispatch-only; full compile suite green
with NO test changes (proof of behavior preservation).

## Notes

- Skip arm stays inline (3-line per-reason logging; not worth a function).
- S04 flips these handlers + `compile_file` + `main()` to `CompileOutcome` and deletes
  `_STATE_MUTATING_SKIPS` + the magic-key dict + dead `_build_owner_block`.
