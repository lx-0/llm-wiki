---
milestone: M027
slice: S02
task: T01
project: llm-wiki
closed: 2026-06-10T15:05:00+0200
verification: passed
---

# M027-S02-T01 -- Summary

## Commits

- `24d2134` -- feat(M027-S02-T01): body-blind folder-index walker
- `f7dc19b` -- plan(M027-S02-T01): body-blind folder-index walker — unmasked per DECISIONS 2026-06-07

## Outcome

`scripts/collectors/folder_index.py` walks one `personal.watched_folders`
entry (kind=local, S01 shape `{id, kind, path, include?, exclude?}`)
**body-blind** — `os.scandir` + `entry.stat(follow_symlinks=False)` only,
never `open()` (test-pinned via poisoned `builtins.open`) — and returns a
`FolderIndex` dataclass: depth-capped tree (`IndexEntry` per dir/file with
rel_path as-is, size, mtime, lowercased ext) + top-N-recent files by mtime
desc + counts (`files/dirs/skipped_excluded/skipped_depth/errors`).
include/exclude are fnmatch globs against rel_path; exclude wins and an
excluded dir is not descended. Symlinks are never followed (recorded as
non-dir entries). PermissionError/OSError fail soft into `counts["errors"]`;
a nonexistent root raises ValueError. Output is deterministic (dirs-first
per level, recent tie-break by rel_path) — the T02/T03 delta-hashing
contract. Stdlib-only module, no config import (knob lifting is T04 with
migration). 7 tests in `tests/test_folder_index_collector.py`.

## Deviations from plan

- **Slice-plan wording "applying the S01 filename-sanitization primitive" was
  stale and NOT implemented** — superseded by DECISIONS 2026-06-07 (metadata
  index is unmasked; the S03 human-approval walk is the content gate). The
  task-plan itself already carried this spec correction; names land as-is.
- Two ambiguities pinned during TDD (documented in the module docstring):
  depth semantics = root children are depth 1, a dir at depth == max_depth is
  enumerated but not descended (counted in `skipped_depth`); include globs
  filter **files only** — dirs are always traversed unless excluded, so
  nested matches stay reachable.
- One test-fixture fix during RED→GREEN: the recent-list test initially left
  background fixture files with "now" mtimes that outranked the pinned ones —
  fixed in the test, not the implementation.

## Follow-ups

- T02 note: slice-plan "Done when" still says "sanitized digest" — read as
  "unmasked digest" per the same DECISIONS supersession when planning
  T02/T04.
- None otherwise — no new decisions, no KNOWLEDGE-worthy gotchas.

## Verification

Command: `uv run pytest tests/test_folder_index_collector.py -q` then
`uv run pytest -q` -- passed. 7/7 new tests green; full suite **1214 passed,
0 failed** (was ~1207 before — no regression).
