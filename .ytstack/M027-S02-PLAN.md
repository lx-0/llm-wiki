---
milestone: M027
slice: S02
project: llm-wiki
created: 2026-06-07T12:21:47+0200
status: planned
task_count: 4
completed_tasks: 4
---

# M027-S02 -- Slice Plan

**Goal:** A body-blind folder-index collector for local roots that writes a
sanitized, delta-aware metadata digest to `raw/index/<root>.md`.

## Tasks

- [x] T01 -- `scripts/collectors/folder_index.py`: walk a local root body-blind (no content reads), build the minimum-viable digest (depth-capped directory tree + recent-change list). (Sanitization clause superseded by DECISIONS 2026-06-07 — index is unmasked; see T01-SUMMARY.)
- [x] T02 -- Render + write the digest to `raw/index/<root-id>.md` (one MD digest per root, single consumer); enforce size caps so it stays prompt-injectable at 1000s of files.
- [x] T03 -- Delta-awareness: mtime/size diff so unchanged trees are skipped; ingest-hash/skip-record discipline (mirror the 0.1.7 fix) so the index isn't rebuilt-then-re-listed forever.
- [x] T04 -- Wire into the `wiki` CLI (`wiki index` verb) + unit tests on a fixture tree (caps respected, delta skip works; sanitization clause superseded by DECISIONS 2026-06-07 — unmasked).

## Done when

All tasks `[x]` and verified. `wiki index` produces a sanitized digest for a
local fixture root; re-running on an unchanged tree is a no-op.

## Notes

Local-only here; SMB/NAS is S06. Minimum index = whatever lets the S03 producer
name a real file. Richer views (biggest/oldest/histogram) are deferred unless a
consumer proves it needs them (M027-CONTEXT Q4). Depends on S01 T04 (sanitization)
and T05 (config).
