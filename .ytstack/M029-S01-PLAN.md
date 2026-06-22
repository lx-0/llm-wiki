---
milestone: M029
slice: S01
project: llm-wiki
created: 2026-06-22T10:44:06+0200
status: in_progress
task_count: 4
completed_tasks: 2
---

# M029-S01 -- Slice Plan

**Goal:** Stand up the Electron app in `desktop/`, give the engine a structured
status contract, and put a swappable bridge between them — so the rest of the
MVP builds on a real, non-brittle foundation.

## Tasks

- [x] T01 -- Scaffold the Electron app in `desktop/`: own `package.json`, main +
  renderer entry, dev-run script. **Toolchain-isolated** from the Python/CLI repo
  — `desktop/.gitignore` for `node_modules`/build output, no interference with
  the repo's uv/pytest CI (decide electron-builder vs electron-forge here, record
  in M029-CONTEXT). App launches to an empty window in dev.
- [x] T02 -- **(RE-SCOPED 2026-06-22, DRY)** Canonical listener-status module in
  `desktop/` (TS) — single source of truth for S02 + S03. Listener status is
  SYSTEM data, not engine data → read it directly: a small **listener registry**
  (one entry: screenpipe — launchd label + db path + mic/sys device patterns) +
  `getListenerStatus()` reading `launchctl` running-state + `~/.screenpipe/db.sqlite`
  freshness (per-device last-chunk, last-capture) into a typed status object. Pure
  freshness logic separated from I/O + unit-tested (vitest). **No Python `wiki
  --json` command** (deferred to the full-GUI expansion; YAGNI for the MVP).
- [ ] T03 -- Wire `getListenerStatus()` to the renderer via IPC (main → preload
  `contextBridge` → renderer), typed end-to-end. The spawn-now/daemon-ready seam
  is retained only for *future* engine-pipeline calls, not listener status.
- [ ] T04 -- Dev smoke test: app launches, calls the bridge, renders the parsed
  status object (raw JSON dump is fine for this slice). Proves the engine↔app path
  end-to-end before any real UI.

## Done when

All tasks `[x]`. `desktop/` Electron app runs in dev, calls the bridge, and shows
live parsed status from the engine's `--json` output. No human-text scraping.

## Notes

Targets **M029** explicitly (STATE.current_milestone is M028 — parallel session).
Cross-tech CI isolation is part of T01, not an afterthought.
