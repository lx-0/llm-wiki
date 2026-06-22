---
milestone: M029
slice: S03
project: llm-wiki
created: 2026-06-22T10:44:06+0200
status: planned
task_count: 4
completed_tasks: 0
---

# M029-S03 -- Slice Plan

**Goal:** A real, glanceable health window and a shippable signed app — the MVP
both audiences can actually run.

## Tasks

- [ ] T01 -- Read-only health window UI: listener running-state (green/red),
  per-device freshness (mic / System-Audio, "Xs ago"), last-capture timestamps,
  live poll (every few seconds) via the S01 bridge. No write paths beyond the
  S02 start/stop control. Catches exactly the "is it running before my meeting"
  failure that motivated this.
- [ ] T02 -- macOS packaging: build a `.app`, **code-sign** (Apple Developer ID)
  + **notarize**. This also gives the app a stable TCC identity (the screenpipe-
  bundle fix, generalised). Document the signing prerequisites for the operator.
- [ ] T03 -- Auto-update wiring (`electron-updater` + a release channel, e.g.
  GitHub Releases) so the app can ship fixes without manual reinstall.
- [ ] T04 -- End-to-end verification on macOS: the signed, notarized `.app`
  launches from `/Applications`, the toggle starts/stops screenpipe, the health
  window shows live freshness, and (if the app holds the screenpipe TCC grants)
  capture works without the separate watchdog. Report what's verified vs deferred.

## Done when

All tasks `[x]`. A signed/notarized `.app` launches, toggles screenpipe, and shows
live health. MVP exit criteria (M029-CONTEXT) met.

## Notes

Targets **M029** explicitly. Auto-update host + signing identity are operator-
provided prerequisites — surface them, don't assume them.
