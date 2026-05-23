---
milestone: M025
slice: S01
task: T03
project: llm-wiki
closed: 2026-05-23T18:58:00+0200
verification: passed
source: post-tool-use-bash-draft
---

# M025-S01-T03 -- Summary

## Commits so far

- `f25abe5` -- feat(M025-S01-T03): capture index — capture_id to source/status map at ingest (2026-05-23T18:54:06Z)

## Outcome

`scripts/core/capture_index.py` is the deterministic `state/capture_index.json`
map (`capture_id → {source_path, created, status}`) the correction loop is built
on. `record(capture_id, *, source_path, created) -> bool` runs the
read-modify-write under an fcntl flock (the `core.usage` pattern) and is
idempotent — if the ID is already present it returns False and leaves the
existing entry untouched, so an S03-set `status: superseded` is NOT reset by a
re-ingest of identical content. `load() -> dict` tolerates a corrupt / partially
written file (returns `{}`) rather than crashing the ingest path. Status
constants `STATUS_OPEN` / `STATUS_SUPERSEDED` are exported for S03. The capture
collector now calls `record()` at ingest after writing each article, with
`source_path = out_path.relative_to(RAW_DIR.parent)` (= `raw/captures/capture-<id>.md`);
an index-write failure is degraded, not fatal — surfaced via `RunResult.errors`,
the article is already on disk. This closes S01: the capture-side spine
(collector + ID + index) is complete; S02 (forward link) and S03 (supersede)
both consume this index.

## Deviations from plan

- **+1 file vs the 3-file estimate (4 total).** As the plan flagged as a
  possibility, `tests/test_capture_collector.py`'s `capture_env` fixture needed
  extending to monkeypatch the index path (`CAPTURE_INDEX_FILE` + `_LOCK_FILE`),
  otherwise a real-run collector test would write to the engine repo's real
  `state/`. Verified post-change: no `state/capture_index.json` pollution.
- **Used `RAW_DIR.parent`, not `ROOT_DIR`, for the relative source_path.** The
  plan named ROOT_DIR; switched to `RAW_DIR.parent` (same value in production)
  because the existing fixture monkeypatches `RAW_DIR` but not `ROOT_DIR` — using
  ROOT_DIR would have raised `ValueError` (out_path not under the un-patched
  ROOT_DIR) in tests. No new import needed.

## Follow-ups

- **S02 (next slice)** consumes `capture_index.load()` for the forward link
  (daily-digest surfaces captures by ID + the brain's interpretation).
- **S03** adds the `status: superseded` writer (an `update_status()` / supersede
  primitive on `capture_index`) honoured by the next compile cycle.
- Carried from T02 (deferred, not a blocker): `docs/setup-capture.md` operator
  setup recipe.
- Pre-existing, unrelated: 4 `tests/test_dream_sampling.py` time-drift failures —
  not in this task diff.

## Verification

Command: `uv run --project .wiki pytest tests/test_capture_index.py tests/test_capture_collector.py -q`
-- passed (23 passed: record adds/idempotent/corrupt-tolerant/distinct-ids;
real run records the entry; re-drop preserves superseded status). Focused
regression (index + collector + migration + daily) 69 passed. No engine
`state/` pollution confirmed.
