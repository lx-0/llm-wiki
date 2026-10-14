---
milestone: M032
slice: S04
task: T04
project: llm-wiki
closed: 2026-10-15T03:05:00+02:00
verification: passed
---

# M032-S04-T04 -- Summary

## Commits

Committed together with this summary under the `M032-S04-T04:` ref — `git log --grep '^M032-S04-T04'`.

## Outcome

`index.html` is a ten-line page that mounts the Svelte panel; `renderer.ts` (872 lines) and
the `panel.html` scaffold are gone, `PAGES` lost `panel`, and `main.ts` needed no change (it
always loaded `index.html`). `index.css` went from 1,661 to 755 lines: what remains is the
Cockpit / Atlas / HUD styling, the entry-type badge they share, the legacy variable aliases and
the one base-button rule (transition + hover/active brightness) their buttons still inherit —
everything the old panel owned is out. The harness captures `index` in the panel's fourteen
states, light and dark, under the strict layout gate, and a surface can now declare a resting
height budget: `index` must request ≤ 640 px in the `fresh` state or the run fails with
`TOO TALL` and `report.json.heightFailures`. The gate's pass/fail rules live in
`scripts/shots/gates.cjs` (`layoutFailures`, `restHeightFailure`) with three vitest cases.
`npm run package` builds the production bundle with the new entry (eight renderer pages, no
panel.html).

## Deviations from plan

- The stylesheet diet was proven, not argued: a one-off probe dumped a computed-style
  fingerprint of the cockpit (80 elements × 50 properties) and atlas (35 elements) DOM before
  and after. The first pass had lost one thing the class-name census could not see — the old
  panel's generic `button { transition: filter, opacity }` + hover/active brightness filters,
  inherited by `.ck-run` and every other cockpit button. Restored as a scoped base rule; the
  second fingerprint is identical for both pages. (The substring census was useless for names
  like `.ok`, `.fill`, `.vault`; the probe is the method, now in KNOWLEDGE.)
- The height gate was watched failing before it was trusted: budget set to 600 → exit 1,
  both fresh captures flagged, `heightFailures` populated; then set to 640.
- The atlas page fails to load (`ERR_FAILED`) when opened right after a destroyed cockpit
  window in the same Electron process; the probe loads one page per process. The harness is
  unaffected (it has always captured atlas after cockpit — different windows, no destroy race
  observed there), noted in case it ever is.
- `npm run shots` / `npm run package` were run as `npm --prefix desktop run …`: from a Claude
  session the shell hook once dropped the leading `cd` and npm looked for `package.json` in
  the repo root (exit 254). Not a code change.

## Follow-ups

- S05-T02 deletes `index.css`, `cockpit.*`, `atlas.*`, `lib/types.ts` — the legacy aliases
  and the base-button rule go with them.
- Header nav "Overview" opens Cockpit until S05-T01 ships the Overview window.
- The `smoke` page (primitives sheet) is deleted at the S05 closeout as planned.

## Verification

Command: `cd desktop && npm test && rtk proxy npm run lint && npm run shots … && test ! -e
src/renderer.ts && test ! -e panel.html && npm run package` — passed (vitest 97 passed / 1
skipped incl. 3 `gates` cases that failed first with "Cannot find module './gates.cjs'"; tsc +
svelte-check 0 / 0; biome 0 errors, 9 warnings all in cockpit.ts / atlas.ts / index.css /
tokens.css; harness 50 captures, 0 page errors, 0 layout failures, 0 height failures,
`panelHeights` light-fresh 639 / dark-fresh 639; `renderer.ts` and `panel.html` absent;
`npm run package` exit 0 → `out/llm-wiki-darwin-arm64/llm-wiki.app`). Reviewed at full size:
`index-light-fresh`, `index-dark-asked`, `index-light-run-done`, `cockpit-dark-default`,
`atlas-dark-default`.
