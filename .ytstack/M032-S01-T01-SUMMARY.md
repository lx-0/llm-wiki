---
milestone: M032
slice: S01
task: T01
project: llm-wiki
closed: 2026-10-14T14:30:00+02:00
verification: passed
---

# M032-S01-T01 -- Summary

## Commits

Committed together with this summary under the `M032-S01-T01:` ref — `git log --grep '^M032-S01-T01'`.

## Outcome

`npm run shots` builds the renderer standalone (`vite build -c vite.renderer.config.ts`, now
carrying Forge's own `base: './'` + `outDir`) and runs `scripts/shots/capture.cjs` under the
project's Electron: 28 offscreen captures (panel × 7 states × light/dark, onboarding/settings
× 2, browse/triage × 2 states × 2 schemes, cockpit + atlas dark) at device scale 2 into
`out/shots/`, plus `report.json` with the panel's requested height per state and any
console/page errors (non-zero exit when a page logged an error). The stub preload
(`scripts/shots/stub-preload.cjs`) serves the four `window.*` domains from
`scripts/shots/fixtures.cjs` and exposes `window.__shots.{heights,fire}` so the capture
script can read auto-fit heights and fire renderer callbacks (`failed` = `compileDone
{ok:false}`). Each window uses an in-memory `partition`, so `localStorage` flags like
`navHintSeen` never leak between captures.

Measured on the real engine (replaces the Playwright estimate in `deslop-arc.md`): panel
requests **1,027 px** fresh, 1,151 asked, 1,542 expanded, 875 no-access, 580 empty — against
the 640 px clamp.

## Deviations from plan

- Fixtures are a `.cjs` module (`build(state, now)`) rather than JSON — timestamps must be
  relative to now for "12m ago" to render.
- 28 PNGs, not the 25 the plan's arithmetic claimed (the table itself was right).
- Electron 42 deprecates the legacy `console-message` positional arguments; the listener uses
  the event object (`event.level`, `event.message`).

## Follow-ups

- `vite build` prints "The CJS build of Vite's Node API is deprecated" because
  `desktop/package.json` has no `"type": "module"` — fold into S01-T02/T04 toolchain work
  (the harness scripts are `.cjs` on purpose and keep working either way).
- The `cockpit`/`atlas` rows of the surface table go away in S05-T02.
- KNOWLEDGE.md: harness gotchas recorded in the desktop section (offscreen windows have no
  vibrancy → solid `backgroundColor`; `additionalArguments` + `sandbox:false` for preload
  parameters; per-window `partition`).

## Verification

Command: `cd desktop && npm run shots && node -e "…report.json… exit 1 on errors"` — passed
(exit 0, 28 PNGs, `errors: {}`; `index-dark-fresh.png` shows the nav-hint, `index-*-failed`
shows "Update failed — try again", `index-*-no-access` the Full-Disk-Access card,
`index-*-running` the 3 of 12 progress bar).
