---
milestone: M029
slice: S01
project: llm-wiki
created: 2026-06-22T10:44:06+0200
status: in_progress
task_count: 4
completed_tasks: 1
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
- [ ] T02 -- Engine `--json` status contract: add structured JSON output for the
  command the app consumes (e.g. `wiki listener-status --json` or extend
  `wiki status --json`) with a stable, documented schema (listener running-state,
  per-device freshness, last-capture timestamps). This is an engine change — goes
  through `config`/migration rules only if a knob is added; otherwise pure additive.
- [ ] T03 -- Bridge abstraction in `desktop/`: a single module the renderer calls;
  **spawn-now** implementation (child-process `wiki ... --json` + direct `launchctl`/
  sqlite reads) behind a **daemon-ready interface** so a warm local daemon can
  replace it later without UI changes. Returns typed status objects, never raw text.
- [ ] T04 -- Dev smoke test: app launches, calls the bridge, renders the parsed
  status object (raw JSON dump is fine for this slice). Proves the engine↔app path
  end-to-end before any real UI.

## Done when

All tasks `[x]`. `desktop/` Electron app runs in dev, calls the bridge, and shows
live parsed status from the engine's `--json` output. No human-text scraping.

## Notes

Targets **M029** explicitly (STATE.current_milestone is M028 — parallel session).
Cross-tech CI isolation is part of T01, not an afterthought.
