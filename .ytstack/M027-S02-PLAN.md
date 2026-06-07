---
milestone: M027
slice: S02
project: llm-wiki
created: 2026-06-07T12:21:47+0200
status: planned
task_count: 4
completed_tasks: 0
---

# M027-S02 -- Slice Plan

**Goal:** A body-blind folder-index collector for local roots that writes a
sanitized, delta-aware metadata digest to `raw/index/<root>.md`.

## Tasks

- [ ] T01 -- `scripts/collectors/folder_index.py`: walk a local root body-blind (no content reads), build the minimum-viable digest (depth-capped directory tree + recent-change list), applying the S01 filename-sanitization primitive to every path before it enters the digest.
- [ ] T02 -- Render + write the digest to `raw/index/<root-id>.md` (one MD digest per root, single consumer); enforce size caps so it stays prompt-injectable at 1000s of files.
- [ ] T03 -- Delta-awareness: mtime/size diff so unchanged trees are skipped; ingest-hash/skip-record discipline (mirror the 0.1.7 fix) so the index isn't rebuilt-then-re-listed forever.
- [ ] T04 -- Wire into the `wiki` CLI (`wiki index` verb) + unit tests on a fixture tree (sanitization applied, caps respected, delta skip works).

## Done when

All tasks `[x]` and verified. `wiki index` produces a sanitized digest for a
local fixture root; re-running on an unchanged tree is a no-op.

## Notes

Local-only here; SMB/NAS is S06. Minimum index = whatever lets the S03 producer
name a real file. Richer views (biggest/oldest/histogram) are deferred unless a
consumer proves it needs them (M027-CONTEXT Q4). Depends on S01 T04 (sanitization)
and T05 (config).
