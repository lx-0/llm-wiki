---
milestone: M029
slice: S01
task: T02
project: llm-wiki
completed: 2026-06-22
status: done
---

# M029-S01-T02 -- Summary

**Canonical listener-status module in `desktop/`, app-direct (DRY re-scope).** Commit `6eb6d9c`.

## Re-scope (why this differs from the original plan)

Operator prompt: "refactor sustainably (DRY) when sensible." On inspection the
original T02 ("engine `--json` command") was the wrong layer: **listener status is
SYSTEM data** (launchd + `~/.screenpipe/db.sqlite`), not wiki-engine data. So the
app reads it directly — no Python `wiki --json` in the poll loop, no engine
config/migration, no cold-spawn. The engine `--json` contract is deferred to the
full-GUI expansion (when the app shows wiki-PIPELINE health) — YAGNI now. Logic
lives **once** in TS as the single source of truth for S02 + S03. Decision recorded
in `M029-CONTEXT.md`.

## What was built

- `desktop/src/listeners/registry.ts` — declarative listener registry (one entry:
  screenpipe); prefigures the engine `listener-lifecycle` registry. Db-path/label
  are config, not hardcoded across the code.
- `desktop/src/listeners/status.ts` — **pure** `channelStatus` / `deriveStatus`
  (freshness + zombie heuristic, no I/O) + **thin I/O** `isRunning` (launchctl),
  `lastChunkMs` (`sqlite3 -readonly`, julianday→epoch-ms for format-robustness,
  `execFileSync` per the shell-injection rule), `getListenerStatus` (nowMs injectable).
  Zombie heuristic mirrors `~/.screenpipe/watchdog.sh` (mic-fresh + system-stale/absent).
- `desktop/src/listeners/status.test.ts` — vitest (org standard, added as devDep).

## Verification (REGEL #1)

- `npx vitest run` → **10/10 green** (pure: fresh/stale/null/clock-skew + zombie
  detected / not-when-stopped / not-when-mildly-stale; + a live I/O smoke test).
- Live primitives confirmed against the real machine: `launchctl list
  com.alex.screenpipe` → running; last mic chunk `2026-06-22 11:06:59` (fresh).
  screenpipe had auto-restarted via `RunAtLoad` after an interim reboot — the
  module reads the real running+fresh state.

## Carry-forward

- T03: wire `getListenerStatus()` to the renderer via IPC (main → preload
  `contextBridge` → renderer), typed end-to-end.
- The launchd label / db path are operator-specific (`alex`) — becomes per-install
  config when the listener-lifecycle subsystem lands.
