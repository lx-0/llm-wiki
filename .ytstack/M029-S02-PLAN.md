---
milestone: M029
slice: S02
project: llm-wiki
created: 2026-06-22T10:44:06+0200
status: done
task_count: 3
completed_tasks: 3
---

# M029-S02 -- Slice Plan

**Goal:** The app can start and stop the screenpipe listener on the fly — the
urgent driver — with the lifecycle logic shipped in-repo, not borrowed from the
operator-local prototypes.

## Tasks

- [x] T01 -- Port the listener-lifecycle logic into shipped code under `desktop/`
  (or an engine `listener-lifecycle` backend, decide ownership per CONTEXT):
  `launchctl bootout/bootstrap/kickstart` + the zombie/freshness probe (mic-fresh
  AND System-Audio-stale → restart), with the 30-min cooldown. **Self-contained**
  — must NOT shell out to `~/.screenpipe/sp` or `~/.screenpipe/watchdog.sh`
  (those stay disposable prototypes; this is the shipped equivalent).
- [x] T02 -- Wire a start/stop control through the bridge (renderer → main IPC →
  lifecycle backend). Reflects real state (running/stopped) and disables itself
  while a transition is in flight.
- [x] T03 -- Verify start/stop actually takes effect: stopping halts DB growth,
  starting resumes it (assert against `~/.screenpipe/db.sqlite` chunk counts
  before/after). Real behaviour, not just "the command returned 0".

## Done when

All tasks `[x]`. Clicking the control starts/stops screenpipe, verified by the DB
halting/resuming. No dependency on the `~/.screenpipe/sp` prototype.

## Notes

Targets **M029** explicitly. The `sp`/watchdog logic is the reference to port;
the artifacts themselves are not shipped and must not be called at runtime.
