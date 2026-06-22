---
milestone: M029
slice: S02
task: T02
project: llm-wiki
completed: 2026-06-22
status: done
---

# M029-S02-T02 -- Summary

**Start/stop control wired over IPC, with a button.** Commit `d2e591f`.

- `ipc.ts` — extended the shared contract: `LISTENER_CONTROL_CHANNEL` +
  `ListenerApi.control(id, action)`.
- `main.ts` — `ipcMain.handle(LISTENER_CONTROL_CHANNEL, …)` dispatches to
  `start/stop/restartListener` by action, **validating** id + action (renderer is a
  trust boundary); logs each result.
- `preload.ts` — exposes `control` via contextBridge.
- `renderer.ts` — a Start/Stop button per listener (label tracks running state),
  disabled while a transition is in flight, re-renders status after.

Verification: `npx vitest run` 12 passed + 1 skipped; the control IPC mirrors the
already-verified status IPC (S01-T03), and the lifecycle backend it calls is
live-verified in T03. The literal button-click GUI path is not headlessly testable
— operator can confirm with one click in the running app.
