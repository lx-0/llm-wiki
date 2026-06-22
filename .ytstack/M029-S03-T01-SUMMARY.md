---
milestone: M029
slice: S03
task: T01
project: llm-wiki
completed: 2026-06-22
status: done
---

# M029-S03-T01 -- Summary

**Live-polling health window.** Commit `8ca7e75`.

- `renderer.ts` — polls `window.listeners.status()` every 3 s (interval cleared on
  `beforeunload`); renders a card per listener: colored state dot
  (running=green / stopped=grey / zombie=amber), mic+sys freshness ("Xs/Xm ago" +
  ✓), last-capture wall-clock (`toLocaleTimeString`), and the Start/Stop button
  (S02), disabled while busy.
- `index.css` — card layout, state colors, tabular-nums for timestamps.

Pure presentation over the already-verified status/control IPC — no backend or
engine change.

## Verification (REGEL #1)

- Dev launch: main log showed **5 status polls in ~18 s** → live polling at the 3 s
  interval works. No errors.
- `npx vitest run` → 12 passed + 1 skipped (live guarded).

## S03 remaining — OPERATOR-GATED

T02 (signing), T03 (auto-update), T04 (signed e2e) need credentials/hosting only the
operator has:
- **T02 macOS signing/notarization** — needs an Apple Developer ID + app-specific
  password + team id. I can prepare `forge.config.ts` (`osxSign: {}` + `osxNotarize`
  via env vars, per the context7 research) + document the prerequisites, but cannot
  execute the signed build.
- **T03 auto-update** — needs a release host (e.g. GitHub Releases) + a publisher
  config. Scaffold-able; full wiring needs the host.
- **T04 signed e2e** — depends on T02. I can verify the UNSIGNED `npm run package`
  produces a launchable `.app` now; the signed/notarized run is operator-gated.
