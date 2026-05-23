---
milestone: M026
slice: S01
project: llm-wiki
created: 2026-05-23T14:09:59+0200
status: planned
task_count: 1
completed_tasks: 0
---

# M026-S01 -- Slice Plan

**Goal:** Introduce the two new types the refactor needs — `CompileOutcome` (what
`compile_file` will return) and the `Route` union (`Skip`/`IndexOnly`/`HealthStub`/
`Compile`, what `decide_route` will return) — with unit tests. **No wiring**: nothing
in `compile.py` calls them yet. A pure, safe, additive foundation slice.

## Tasks

- [ ] T01 -- Add `CompileOutcome` to `compile_stages/types.py` (mirrors
  `CompileResult` — string `failure_kind`/`failure_detail`, keeps `types.py`
  dependency-light) and the `Route` union to a new `compile_stages/route.py`
  (`Skip`/`IndexOnly`/`HealthStub`/`Compile` frozen dataclasses; `Compile` carries
  `CompileMetadata` + `ClassifyResult`). Export both from `compile_stages/__init__.py`.
  Unit tests: construction, frozen-ness, field shapes, the four `Route` variants.

## Done when

T01 marked `[x]` and verified via `ytstack:summarize-task`. `pytest` green; no
import cycle (`route.py` imports `types` + `classify`, neither imports `route`).

## Notes

- `decide_route()` itself is **S02**, not here — S01 only defines the types it returns.
- `ClassifyResult` (kind/chunks) is the existing return type of
  `compile_stages/classify.py:classify()`; `Compile` carries it so the route decision
  fully describes single-vs-chunked without re-running classify.
- `CompileOutcome.failure_kind`/`failure_detail` are strings (not a `FailureClass`
  object) for consistency with `CompileResult` and to keep `types.py` import-free of
  `core.sdk_helpers`; `main()` reconstructs `FailureClass` when it needs the abort
  heuristic (it already does this at `compile.py:791`).
