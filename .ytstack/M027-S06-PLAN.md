---
milestone: M027
slice: S06
project: llm-wiki
created: 2026-06-07T12:21:47+0200
status: planned
task_count: 4
completed_tasks: 0
---

# M027-S06 -- Slice Plan

**Goal:** Extend index + backend to remote NAS shares over SMB, running the
periodic build and the body reads outside the Claude-Code TCC sandbox.

## Tasks

- [ ] T01 -- SMB reader (`smbprotocol`) for the index build over a NAS share (`kind: smb` in `watched_folders`); body-blind walk + sanitization reused from S02; per `nas-ingest.md` mechanics.
- [ ] T02 -- Out-of-sandbox reader for CloudStorage/NAS body reads (the TCC wall hits the backend, not just the index): a LaunchAgent-run reader resolves `folder-deep-scan` requests for those roots and emits answer artifacts the in-session loop then consumes. Plain-local stays in-session (S04).
- [ ] T03 -- Periodic scheduler (LaunchAgent / system-scheduler, per `system-level-scheduler.md`) for the index build; frequency knob in config; runs even when Claude Code isn't open.
- [ ] T04 -- e2e on >=1 real NAS root: index built + a `folder-deep-scan` answer derived from a NAS file, verified; no raw body in the vault.

## Done when

All tasks `[x]` and verified. A NAS share is indexed and a folder-scan answer is
produced from it via the out-of-sandbox reader, on a periodic schedule.

## Notes

The remote half + TCC-safe execution. Heaviest infra slice. Depends on S02
(local index shape), S04 (in-place contract), and `nas-ingest.md` /
`system-level-scheduler.md`. Exit criteria #4 (NAS root), #5 (out-of-sandbox),
#7 (failure/quarantine on SMB).
