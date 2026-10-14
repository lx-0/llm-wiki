---
milestone: M032
slice: S03
task: T04
project: llm-wiki
closed: 2026-10-14T22:55:00+02:00
verification: passed
---

# M032-S03-T04 -- Summary

## Commits

Committed together with this summary under the `M032-S03-T04:` ref — `git log --grep '^M032-S03-T04'`.

## Outcome

`index.css` lost the Triage, Settings, Onboarding and Browse blocks plus their orphaned helpers
(`.switch`, `.chip`, `.t-task/.t-idea/.t-note`, the Browse scrollbar rules, `.btn-primary/.btn-ghost`)
— 2,348 → 1,661 lines; a consumer grep over the surviving old sources (`renderer.ts`,
`cockpit.ts`, `atlas.ts`, their HTML) found zero class references without a rule, and the old
panel / cockpit / atlas still render without console errors. The harness now runs a DOM layout
audit on every capture (`scripts/shots/audit.cjs`): text leaves are checked for clipped text,
off-screen text and text-on-text overlap > 100 px² using per-line client rects cut to each
element's visible region; `report.json` carries `layout` per capture and `layoutFailures` for
the token-system windows (settings, onboarding, browse, triage, smoke), which fail the run.
All strict pages are clean in light and dark.

## Deviations from plan

- Legacy pages (panel, cockpit, atlas) are audited and reported but never fail the run — they
  are replaced in S04/S05 and the plan's "clipped fails only on Svelte windows" became "any
  finding fails only on Svelte windows" once the old panel showed up with three findings per
  state.
- Two audit false-positive classes were fixed before the gate meant anything: a wrapped inline
  `<b>` is not one rectangle across two lines (per-line `getClientRects`), and rows scrolled past
  the end of a list are not "behind the footer" (boxes cut to the nearest clipping ancestor).

## Follow-ups

- The old panel reports one real overlap in every state (`button.ghost "Refresh"` over
  `button#quit "Quit"`, 809 px²) — dies with `renderer.ts` in S04; S04-T04 adds `index` to the
  strict pages.
- S03 complete → `ytstack:reassess-roadmap`, then S04 (panel rebuild).

## Verification

Command: `cd desktop && npm test && rtk proxy npm run lint && npm run shots` + the report check —
passed (vitest 75 passed / 1 skipped; biome 0 errors; 36 captures, 0 page errors, 0 layout
failures; `strict pages clean`).
