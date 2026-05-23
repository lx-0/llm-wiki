---
milestone: M026
slice: S03
task: T01
project: llm-wiki
closed: 2026-05-23T15:25:00+0200
verification: passed
---

# M026-S03-T01 -- Summary

## Outcome

`compile_file` is now pure dispatch — 404 → 62 lines. Its three execution arms became
module-level functions in `compile.py`: `_run_index_only(source, rel_path, route)`
(source-and-final index-write + ingest mark), `_run_health_stub(source, rel_path)`
(deterministic stub record), and `async _run_compile_route(source, content, rel_path,
route)` (dispatch log + memory pre-pass + chunk/single `compile_source`). `compile_file`
reads content, calls `decide_route`, logs Skip reasons inline, and dispatches to the
handlers. Bodies are verbatim — same dict returns, same behavior.

## Deviations from plan

- Handlers kept **in `compile.py`** (not a separate `compile_stages/execute.py` as the
  design doc sketched). They use compile.py's I/O constants; co-locating avoids a second
  round of test-monkeypatch churn and keeps them next to their deps. Deepening goal
  (compile_file = thin dispatch) met either way. Recorded as a deliberate refinement.

## Follow-ups

- none net-new. S04 flips the handlers + compile_file + main() to `CompileOutcome` and
  deletes `_STATE_MUTATING_SKIPS` + the magic-key dict + dead `_build_owner_block`.

## Verification

Command: `pytest tests/ -k compile` — 126 passed with ZERO test changes (the strongest
proof of behavior preservation for a pure extraction). `compile.py` parses; imports
clean. Committed `e6c04df`.
