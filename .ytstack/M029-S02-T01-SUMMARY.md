---
milestone: M029
slice: S02
task: T01
project: llm-wiki
completed: 2026-06-22
status: done
---

# M029-S02-T01 -- Summary

**Listener lifecycle actions in `desktop/` (launchctl start/stop/restart).** Commit `fab35ec`.

## What was built

- `desktop/src/listeners/lifecycle.ts` — `startListener` (bootstrap, no-op if
  running), `stopListener` (bootout, no-op if stopped), `restartListener`
  (kickstart -k / bootstrap). All via `execFileSync('launchctl', [...])` (array
  args — shell-injection-safe). **Reuses `isRunning` from `status.ts`** (DRY — no
  duplicate launchctl-state logic). Pure `guiDomain` / `guiDomainTarget` helpers
  separated for testing. Each action returns `{action, ok, noop?, error?}`.
- `desktop/src/listeners/registry.ts` — added `plistPath` (needed for bootstrap).
- `desktop/src/listeners/lifecycle.test.ts` — vitest for the pure domain helpers.

## DRY / sustainability

Ports the verified `~/.screenpipe/sp` prototype logic but is **self-contained** —
the prototype is not called at runtime. With S02-T01 the app now owns both halves
of the listener control (read via `status.ts`, act via `lifecycle.ts`) over one
shared registry — the in-repo replacement the eng-review required.

## Verification (REGEL #1)

- `npx vitest run` → **12/12 green** (10 status + 2 lifecycle pure helpers).
- Live start/stop against the real launchd service (DB halt/resume) is **S02-T03**,
  kept separate so the operator's running listener is toggled only at the explicit
  verification step.

## Carry-forward

- T02: expose start/stop over IPC + a button in the renderer (mirrors the
  S01-T03 IPC pattern; disable the button while a transition is in flight).
- T03: live verify start→stop→start with DB halt/resume.
