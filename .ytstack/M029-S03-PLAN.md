---
milestone: M029
slice: S03
project: llm-wiki
created: 2026-06-22T10:44:06+0200
status: planned
task_count: 4
completed_tasks: 1
---

# M029-S03 -- Slice Plan

**Goal:** A real, glanceable health window and a shippable signed app — the MVP
both audiences can actually run.

## Tasks

- [x] T01 -- Read-only health window UI: listener running-state (green/red),
  per-device freshness (mic / System-Audio, "Xs ago"), last-capture timestamps,
  live poll (every few seconds) via the S01 bridge. No write paths beyond the
  S02 start/stop control. Catches exactly the "is it running before my meeting"
  failure that motivated this.
- [~] T02 -- macOS packaging. **CONFIG PREPARED, signing OPERATOR-GATED** (commit
  `6cc9ab5`): `forge.config.ts` has env-gated `osxSign`/`osxNotarize` (prereqs
  documented inline); unsigned `npm run package` verified → built + launched
  `out/desktop-darwin-arm64/desktop.app`. The actual signed+notarized build needs
  the operator's Apple Developer ID (`APPLE_ID`/`APPLE_PASSWORD`/`APPLE_TEAM_ID` +
  a "Developer ID Application" cert). Not executable by the agent.
- [ ] T03 -- Auto-update wiring. **DEFERRED — needs a release host decision**
  (GitHub Releases vs other) + publisher config. Not scaffolded; pick the host first.
- [~] T04 -- E2E. **UNSIGNED path verified** (package builds + .app launches; toggle
  + live health verified in S02-T03 / S03-T01). The **signed/notarized** `.app`
  from `/Applications` + TCC-grant inheritance is operator-gated (depends on T02).

## Done when

Functional MVP (toggle + live health) — **DONE + verified** (S01, S02, S03-T01).
Distribution (signed `.app` + auto-update) — operator-gated remainder (T02 signing,
T03 host, T04 signed e2e). This is the milestone-handoff line.

## Notes

Targets **M029** explicitly. Auto-update host + signing identity are operator-
provided prerequisites — surface them, don't assume them.
